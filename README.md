    # SigmaOS-NVIDIA

    NVIDIA prime / offload GPU management

    Part of the **SigmaOS** sovereign operating-system ecosystem — a multi-repository
    distribution modelled on Linux Mint and Omarchy Linux. See the parent
    [`SigmaOS`](https://github.com/AaryanSinghChauhan09/SigmaOS) repository for the
    full component index.

    ## Upstream inspirations
    - https://github.com/linuxmint/nvidia-prime

    ## Design principles applied
    - **Plan Before Apply**
- **Least Astonishment**
- **Fail-Fast**
- **Information Hiding**
- **KISS**
- **Deterministic Testing**

    ## Usage
    Verbs: `detect, recommend, install-plan, prime`

    ```
    $ sigma-drivers detect --facts pci.txt
$ sigma-drivers recommend --facts pci.txt --available drivers.txt
$ sigma-drivers install-plan --driver nvidia-driver-535
$ sigma-drivers prime --mode on-demand

    ```

    ## Build & test
    ```
    make build
    make test
    ```

    ## Licence
    GNU General Public License v3.0 (FOSS).
