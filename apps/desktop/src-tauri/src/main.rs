#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{BufRead, BufReader, Write};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use tauri::{AppHandle, Emitter, State};

struct LspState {
    child: Mutex<Option<Child>>,
    stdin: Mutex<Option<ChildStdin>>,
}

#[tauri::command]
fn start_clangd(app: AppHandle, state: State<'_, LspState>) -> Result<String, String> {
    stop_clangd_inner(&state)?;

    let which = Command::new("which")
        .arg("clangd")
        .output()
        .map_err(|err| format!("failed to look up clangd: {err}"))?;
    if !which.status.success() {
        return Err("clangd not found on PATH".into());
    }
    let path = String::from_utf8_lossy(&which.stdout).trim().to_string();
    if path.is_empty() {
        return Err("clangd not found on PATH".into());
    }

    let mut child = Command::new(&path)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|err| format!("failed to spawn clangd: {err}"))?;

    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "clangd stdout unavailable".to_string())?;
    let stdin = child
        .stdin
        .take()
        .ok_or_else(|| "clangd stdin unavailable".to_string())?;

    *state.stdin.lock().map_err(|_| "lsp stdin lock poisoned")? = Some(stdin);
    *state.child.lock().map_err(|_| "lsp child lock poisoned")? = Some(child);

    thread::spawn(move || {
        let mut reader = BufReader::new(stdout);
        loop {
            let mut header = String::new();
            let mut content_length: Option<usize> = None;
            loop {
                header.clear();
                if reader.read_line(&mut header).ok().unwrap_or(0) == 0 {
                    return;
                }
                if header == "\r\n" || header == "\n" {
                    break;
                }
                if let Some(rest) = header
                    .strip_prefix("Content-Length:")
                    .or_else(|| header.strip_prefix("content-length:"))
                {
                    content_length = rest.trim().parse().ok();
                }
            }
            let Some(len) = content_length else {
                continue;
            };
            let mut body = vec![0u8; len];
            if std::io::Read::read_exact(&mut reader, &mut body).is_err() {
                return;
            }
            if let Ok(payload) = String::from_utf8(body) {
                let _ = app.emit("lsp-message", payload);
            }
        }
    });

    Ok(path)
}

#[tauri::command]
fn lsp_send(state: State<'_, LspState>, payload: String) -> Result<(), String> {
    let mut guard = state.stdin.lock().map_err(|_| "lsp stdin lock poisoned")?;
    let stdin = guard
        .as_mut()
        .ok_or_else(|| "clangd session not started".to_string())?;
    let packet = format!("Content-Length: {}\r\n\r\n{}", payload.len(), payload);
    stdin
        .write_all(packet.as_bytes())
        .map_err(|err| format!("failed to write to clangd: {err}"))?;
    stdin
        .flush()
        .map_err(|err| format!("failed to flush clangd stdin: {err}"))?;
    Ok(())
}

#[tauri::command]
fn stop_clangd(state: State<'_, LspState>) -> Result<(), String> {
    stop_clangd_inner(&state)
}

fn stop_clangd_inner(state: &State<'_, LspState>) -> Result<(), String> {
    *state.stdin.lock().map_err(|_| "lsp stdin lock poisoned")? = None;
    if let Some(mut child) = state
        .child
        .lock()
        .map_err(|_| "lsp child lock poisoned")?
        .take()
    {
        let _ = child.kill();
        let _ = child.wait();
    }
    Ok(())
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .manage(LspState {
            child: Mutex::new(None),
            stdin: Mutex::new(None),
        })
        .invoke_handler(tauri::generate_handler![start_clangd, lsp_send, stop_clangd])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
