#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::fs;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::Duration;

use serde::Serialize;
use tauri::path::BaseDirectory;
use tauri::{Manager, RunEvent, State};

#[tauri::command]
fn ping() -> String {
  "ok".to_string()
}

#[derive(Default)]
struct ServiceChildren {
  postgres: Option<Child>,
  qdrant: Option<Child>,
  server: Option<Child>,
}

struct ServiceState(Mutex<ServiceChildren>);

#[derive(Serialize)]
struct ServiceStatus {
  postgres: bool,
  qdrant: bool,
  server: bool,
}

fn resolve_bin(app: &tauri::AppHandle, name: &str) -> Option<PathBuf> {
  let path = app
    .path()
    .resolve(format!("bin/{}", name), BaseDirectory::Resource)
    .ok()?;

  #[cfg(target_os = "windows")]
  path.set_extension("exe");

  Some(path)
}

fn ensure_postgres_data(app: &tauri::AppHandle) -> Option<PathBuf> {
  let data_root = app.path().app_data_dir().ok()?;
  let pg_data = data_root.join("postgres");
  fs::create_dir_all(&pg_data).ok()?;

  if pg_data.join("PG_VERSION").exists() {
    return Some(pg_data);
  }

  let initdb_path = resolve_bin(app, "initdb")?;
  let status = Command::new(initdb_path)
    .args([
      "-D",
      pg_data.to_string_lossy().as_ref(),
      "-A",
      "trust",
      "-U",
      "postgres",
      "--encoding",
      "UTF8",
    ])
    .stdout(Stdio::null())
    .stderr(Stdio::null())
    .status()
    .ok()?;

  if status.success() {
    Some(pg_data)
  } else {
    None
  }
}

fn start_postgres(app: &tauri::AppHandle) -> Option<Child> {
  let pg_data = ensure_postgres_data(app)?;
  let postgres_path = resolve_bin(app, "postgres")?;

  Command::new(postgres_path)
    .args([
      "-D",
      pg_data.to_string_lossy().as_ref(),
      "-h",
      "127.0.0.1",
      "-p",
      "5432",
    ])
    .stdout(Stdio::null())
    .stderr(Stdio::null())
    .spawn()
    .ok()
}

fn ensure_database(app: &tauri::AppHandle) {
  let createdb_path = match resolve_bin(app, "createdb") {
    Some(path) => path,
    None => return,
  };

  let _ = Command::new(createdb_path)
    .args(["-h", "127.0.0.1", "-p", "5432", "-U", "postgres", "hivemind"])
    .env("PGUSER", "postgres")
    .stdout(Stdio::null())
    .stderr(Stdio::null())
    .status();
}

fn start_qdrant(app: &tauri::AppHandle) -> Option<Child> {
  let qdrant_path = resolve_bin(app, "qdrant")?;
  let data_root = app.path().app_data_dir().ok()?;
  let qdrant_storage = data_root.join("qdrant");
  fs::create_dir_all(&qdrant_storage).ok()?;

  Command::new(qdrant_path)
    .env("QDRANT__SERVICE__HTTP_PORT", "6333")
    .env("QDRANT__SERVICE__GRPC_PORT", "6334")
    .env(
      "QDRANT__STORAGE__STORAGE_PATH",
      qdrant_storage.to_string_lossy().as_ref(),
    )
    .stdout(Stdio::null())
    .stderr(Stdio::null())
    .spawn()
    .ok()
}

fn start_local_server(app: &tauri::AppHandle) -> Option<Child> {
  let server_path = resolve_bin(app, "hivemind-cloud")?;
  let server_dir = server_path.parent()?.to_path_buf();

  let mut command = Command::new(server_path);
  command
    .current_dir(server_dir)
    .env("HIVEMIND_SERVER_HOST", "127.0.0.1")
    .env("HIVEMIND_SERVER_PORT", "8000");

  command.spawn().ok()
}

fn refresh_status(children: &mut ServiceChildren) -> ServiceStatus {
  let postgres = child_running(&mut children.postgres);
  let qdrant = child_running(&mut children.qdrant);
  let server = child_running(&mut children.server);

  ServiceStatus {
    postgres,
    qdrant,
    server,
  }
}

fn child_running(child: &mut Option<Child>) -> bool {
  if let Some(proc) = child.as_mut() {
    match proc.try_wait() {
      Ok(Some(_)) => {
        *child = None;
        false
      }
      Ok(None) => true,
      Err(_) => true,
    }
  } else {
    false
  }
}

fn start_all(app: &tauri::AppHandle, children: &mut ServiceChildren) {
  if children.postgres.is_none() {
    children.postgres = start_postgres(app);
    if children.postgres.is_some() {
      thread::sleep(Duration::from_secs(2));
      ensure_database(app);
    }
  }

  if children.qdrant.is_none() {
    children.qdrant = start_qdrant(app);
    thread::sleep(Duration::from_secs(1));
  }

  if children.server.is_none() {
    children.server = start_local_server(app);
  }
}

fn stop_all(children: &mut ServiceChildren) {
  if let Some(mut child) = children.server.take() {
    let _ = child.kill();
  }
  if let Some(mut child) = children.qdrant.take() {
    let _ = child.kill();
  }
  if let Some(mut child) = children.postgres.take() {
    let _ = child.kill();
  }
}

#[tauri::command]
fn get_local_status(state: State<ServiceState>) -> ServiceStatus {
  let mut children = state.0.lock().expect("service lock");
  refresh_status(&mut children)
}

#[tauri::command]
fn start_local_services(app: tauri::AppHandle, state: State<ServiceState>) -> ServiceStatus {
  let mut children = state.0.lock().expect("service lock");
  start_all(&app, &mut children);
  refresh_status(&mut children)
}

#[tauri::command]
fn stop_local_services(state: State<ServiceState>) -> ServiceStatus {
  let mut children = state.0.lock().expect("service lock");
  stop_all(&mut children);
  refresh_status(&mut children)
}

fn main() {
  let app = tauri::Builder::default()
    .manage(ServiceState(Mutex::new(ServiceChildren::default())))
    .invoke_handler(tauri::generate_handler![
      ping,
      get_local_status,
      start_local_services,
      stop_local_services
    ])
    .setup(|app| {
      let state = app.state::<ServiceState>();
      let mut children = state.0.lock().expect("service lock");
      start_all(app.handle(), &mut children);
      Ok(())
    })
    .build(tauri::generate_context!())
    .expect("error while running tauri application");

  app.run(|app_handle, event| {
    if let RunEvent::ExitRequested { .. } = event {
      if let Ok(mut guard) = app_handle.state::<ServiceState>().0.lock() {
        stop_all(&mut guard);
      }
    }
  });
}
