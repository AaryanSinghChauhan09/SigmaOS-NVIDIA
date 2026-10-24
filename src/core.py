"""Driver manager for SigmaOS-drivers / SigmaOS-NVIDIA (mintdrivers, nvidia-prime).

Principles: detection is pure (injected facts, no real lspci), recommendations
are deterministic rules with explanations, installs are plans (never executed
here), prime switching is validated against known modes.
"""
import re, json, argparse, sys

ENGINE = {
    "name": "sigma-drivers",
    "summary": "Detect hardware, recommend drivers, plan installs and PRIME switches",
    "language": "python",
    "verbs": ["detect", "recommend", "install-plan", "prime"],
    "principles": ["Plan Before Apply", "Least Astonishment", "Fail-Fast",
                   "Information Hiding", "KISS", "Deterministic Testing"],
}

cli_doc = """\
$ sigma-drivers detect --facts pci.txt
$ sigma-drivers recommend --facts pci.txt --available drivers.txt
$ sigma-drivers install-plan --driver nvidia-driver-535
$ sigma-drivers prime --mode on-demand
"""

PCI_RE = re.compile(
    r"^(?P<slot>[\da-f:.]+)\s+(?P<cls>[^:]+):\s+(?P<desc>[^(]*?)\s*"
    r"\[(?P<vid>[\da-f]{4}):(?P<did>[\da-f]{4})\]"
    r"(?:\s*\((?P<rev>[^)]*)\))?\s*$")

KNOWN = {
    "10de": ("nvidia", "nouveau"),          # NVIDIA
    "1002": ("amdgpu", "radeon"),           # AMD/ATI
    "8086": ("i915", "modesetting"),        # Intel
}
PRIME_MODES = ("intel", "nvidia", "on-demand")


class DriverError(Exception):
    pass


def parse_pci(text):
    """Pure parse of `lspci -nn`-style lines -> device dicts."""
    devices = []
    for line in text.splitlines():
        line = line.strip()
        if not line or not line[0].isdigit():
            continue
        m = PCI_RE.match(line)
        if not m:
            continue
        cls = m.group("cls").lower()
        if "vga" not in cls and "3d" not in cls and "display" not in cls:
            continue
        desc = m.group("desc").strip()
        vendor = desc.split(" Corporation")[0].split()[0] if desc else "unknown"
        devices.append({
            "slot": m.group("slot"),
            "vendor": vendor,
            "vendor_id": m.group("vid").lower(),
            "device_id": m.group("did").lower(),
            "model": desc,
        })
    return devices


def recommend(devices, available=()):
    """Deterministic kernel-driver vs proprietary recommendation per device."""
    if not devices:
        raise DriverError("no display devices detected")
    recs = []
    for dev in devices:
        open_driver, prop_hint = KNOWN.get(dev["vendor_id"], (None, None))
        if dev["vendor_id"] == "10de":
            props = [a for a in available if a.startswith("nvidia-driver")]
            if props:
                driver = sorted(props)[-1]  # highest version wins
                rec = {"device": dev["model"], "driver": driver,
                       "kind": "proprietary",
                       "reason": "proprietary NVIDIA driver gives CUDA/Vulkan support"}
            else:
                driver = "nouveau"
                rec = {"device": dev["model"], "driver": driver, "kind": "open",
                       "reason": "no nvidia-driver package available; using nouveau"}
        elif dev["vendor_id"] == "1002":
            rec = {"device": dev["model"], "driver": "amdgpu", "kind": "in-kernel",
                   "reason": "AMD GPUs use the in-kernel amdgpu driver"}
        elif dev["vendor_id"] == "8086":
            rec = {"device": dev["model"], "driver": "i915", "kind": "in-kernel",
                   "reason": "Intel GPUs use the in-kernel i915 driver"}
        else:
            rec = {"device": dev["model"], "driver": open_driver or "unknown",
                   "kind": "unknown",
                   "reason": f"unrecognized vendor {dev['vendor_id']}; generic driver"}
        recs.append(rec)
    return recs


def plan_install(driver, current="nouveau"):
    """Pure: apt install plan + nouveau blacklist + initramfs refresh."""
    if not re.match(r"^[a-z0-9][a-z0-9+.-]*$", driver):
        raise DriverError(f"invalid package name: {driver!r}")
    blacklist = None
    if driver.startswith("nvidia"):
        blacklist = ("blacklist nouveau", "options nouveau modeset=0",
                     "alias nouveau off")
    steps = [
        {"phase": "install", "cmd": f"apt-get install -y {driver}"},
        {"phase": "blacklist", "cmd": f"write /etc/modprobe.d/blacklist-{driver}.conf",
         "content": blacklist},
        {"phase": "initramfs", "cmd": "update-initramfs -u"},
        {"phase": "reboot", "cmd": "reboot", "required": True},
    ]
    return {"driver": driver, "replacing": current, "steps": steps,
            "summary": f"install {driver}, blacklist {current}, refresh initramfs, reboot"}


def plan_prime(mode, env=None):
    """Pure: PRIME output-switch plan. Validated against known modes."""
    if mode not in PRIME_MODES:
        raise DriverError(f"unknown prime mode {mode!r}; choose from {PRIME_MODES}")
    plan = {"mode": mode, "cmd": f"prime-select {mode}", "env": {}}
    if mode == "intel":
        plan["env"] = {"DRI_PRIME": "0"}
        plan["note"] = "use integrated GPU; lowest power"
    elif mode == "nvidia":
        plan["env"] = {"DRI_PRIME": "1"}
        plan["note"] = "use discrete NVIDIA GPU always"
    else:  # on-demand
        plan["env"] = {"__NV_PRIME_RENDER_OFFLOAD": "1",
                       "__GLX_VENDOR_LIBRARY_NAME": "nvidia"}
        plan["note"] = "run apps with: prime-run <command>"
    if env:
        plan["env"] = {**plan["env"], **env}
    return plan


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=ENGINE["name"], description=ENGINE["summary"])
    sub = p.add_subparsers(dest="cmd", required=True)
    det = sub.add_parser("detect", help="detect display devices from lspci facts")
    det.add_argument("--facts", required=True, help="file with lspci -nn output")
    rec = sub.add_parser("recommend", help="recommend drivers for detected devices")
    rec.add_argument("--facts", required=True)
    rec.add_argument("--available", help="file with available driver package names")
    ins = sub.add_parser("install-plan", help="plan a driver install (dry-run)")
    ins.add_argument("--driver", required=True)
    ins.add_argument("--replacing", default="nouveau")
    pr = sub.add_parser("prime", help="plan an NVIDIA PRIME mode switch")
    pr.add_argument("--mode", required=True)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "detect":
            with open(args.facts) as fh:
                devices = parse_pci(fh.read())
            if not devices:
                print("no display devices detected")
                return 1
            for d in devices:
                print(f"{d['slot']}  {d['vendor']} [{d['vendor_id']}:{d['device_id']}]  {d['model']}")
        elif args.cmd == "recommend":
            with open(args.facts) as fh:
                devices = parse_pci(fh.read())
            available = []
            if args.available:
                with open(args.available) as fh:
                    available = [l.strip() for l in fh if l.strip()]
            for r in recommend(devices, available):
                print(f"{r['device']}: {r['driver']} ({r['kind']}) -- {r['reason']}")
        elif args.cmd == "install-plan":
            print(json.dumps(plan_install(args.driver, args.replacing), indent=2))
        elif args.cmd == "prime":
            print(json.dumps(plan_prime(args.mode), indent=2))
        return 0
    except (DriverError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def self_test() -> None:
    pci = """\
00:02.0 VGA compatible controller: Intel Corporation UHD Graphics 630 [8086:3e9b] (rev 02)
01:00.0 3D controller: NVIDIA Corporation GA104M [GeForce RTX 3070 Mobile] [10de:249d] (rev a1)
02:00.0 Network controller: Intel Corporation Wi-Fi 6 AX200 [8086:2723]
00:1f.0 ISA bridge: Intel Corporation Cannon Point-LP [8086:9d84]
"""
    devices = parse_pci(pci)
    assert len(devices) == 2  # wifi + ISA bridge filtered out
    assert devices[0]["vendor"].startswith("Intel")
    assert devices[1]["vendor_id"] == "10de"
    assert devices[1]["model"].startswith("NVIDIA")

    recs = recommend(devices, available=["nvidia-driver-525", "nvidia-driver-535"])
    by_dev = {r["device"]: r for r in recs}
    nvidia = [r for r in recs if r["kind"] == "proprietary"]
    assert len(nvidia) == 1
    assert nvidia[0]["driver"] == "nvidia-driver-535"  # highest version wins
    intel = [r for r in recs if r["device"].startswith("Intel")][0]
    assert intel["driver"] == "i915" and intel["kind"] == "in-kernel"

    # no proprietary package -> fall back to nouveau with reason
    recs2 = recommend([devices[1]], available=[])
    assert recs2[0]["driver"] == "nouveau"
    assert "nouveau" in recs2[0]["reason"]

    plan = plan_install("nvidia-driver-535")
    assert plan["steps"][0]["cmd"] == "apt-get install -y nvidia-driver-535"
    assert plan["steps"][1]["content"][0] == "blacklist nouveau"
    assert plan["steps"][-1]["required"] is True
    assert plan_install("mesa-utils")["steps"][1]["content"] is None

    try:
        plan_install("bad pkg; rm -rf /")
    except DriverError:
        pass
    else:
        raise AssertionError("shell metachars not rejected")

    prime = plan_prime("on-demand")
    assert prime["env"]["__NV_PRIME_RENDER_OFFLOAD"] == "1"
    assert plan_prime("intel")["env"]["DRI_PRIME"] == "0"
    assert plan_prime("nvidia")["cmd"] == "prime-select nvidia"
    try:
        plan_prime("hybrid-max")
    except DriverError:
        pass
    else:
        raise AssertionError("bad prime mode not caught")

    try:
        recommend([])
    except DriverError:
        pass
    else:
        raise AssertionError("empty device list not caught")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
