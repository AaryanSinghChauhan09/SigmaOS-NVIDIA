//! Configuration for SigmaOS-nvidia

use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::env;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    pub verbose: bool,
    pub dry_run: bool,
    pub config_path: String,
}

impl Config {
    pub fn new() -> Result<Self> {
        Ok(Config {
            verbose: env::var("VERBOSE").is_ok(),
            dry_run: env::var("DRY_RUN").is_ok(),
            config_path: env::var("CONFIG_PATH")
                .unwrap_or_else(|_| "/etc/sigmaos/config.toml".to_string()),
        })
    }

    pub fn from_file(path: &str) -> Result<Self> {
        let content = std::fs::read_to_string(path)?;
        let config: Config = toml::from_str(&content)?;
        Ok(config)
    }
}
