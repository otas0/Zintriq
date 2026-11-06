#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::Command;

#[tauri::command]
fn start_clangd() -> Result<String, String> {
    // Explicit user action only: probe PATH for clangd. Full stdio LSP wiring stays optional.
    let output = Command::new("which")
        .arg("clangd")
        .output()
        .map_err(|err| format!("failed to look up clangd: {err}"))?;
    if !output.status.success() {
        return Err("clangd not found on PATH".into());
    }
    let path = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if path.is_empty() {
        return Err("clangd not found on PATH".into());
    }
    Ok(path)
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .invoke_handler(tauri::generate_handler![start_clangd])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
