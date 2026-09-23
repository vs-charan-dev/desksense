// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager, WindowEvent,
};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, Shortcut};

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .setup(|app| {
            let main_window = app.get_webview_window("main").unwrap();

            // Intercept window close event to hide window instead of quitting (P3-01)
            let window_clone = main_window.clone();
            main_window.on_window_event(move |event| {
                if let WindowEvent::CloseRequested { api, .. } = event {
                    api.prevent_close();
                    let _ = window_clone.hide();
                }
            });

            // Build Tray Menu items (P3-02)
            let open_item = MenuItem::with_id(app, "open_dashboard", "Open Dashboard", true, None::<&str>)?;
            let pause_15m = MenuItem::with_id(app, "pause_15m", "Pause 15 minutes", true, None::<&str>)?;
            let pause_1h = MenuItem::with_id(app, "pause_1h", "Pause 1 hour", true, None::<&str>)?;
            let resume_item = MenuItem::with_id(app, "resume", "Resume Monitoring", true, None::<&str>)?;
            let recalibrate_item = MenuItem::with_id(app, "recalibrate", "Recalibrate Posture", true, None::<&str>)?;
            let settings_item = MenuItem::with_id(app, "settings", "Settings", true, None::<&str>)?;
            let quit_item = MenuItem::with_id(app, "quit", "Quit DeskSense", true, None::<&str>)?;

            let tray_menu = Menu::with_items(
                app,
                &[
                    &open_item,
                    &pause_15m,
                    &pause_1h,
                    &resume_item,
                    &recalibrate_item,
                    &settings_item,
                    &quit_item,
                ],
            )?;

            // Build Tray Icon
            let _tray = TrayIconBuilder::new()
                .menu(&tray_menu)
                .tooltip("DeskSense — ● Monitoring")
                .on_menu_event(move |app_handle, event| {
                    match event.id.as_ref() {
                        "open_dashboard" => {
                            if let Some(win) = app_handle.get_webview_window("main") {
                                let _ = win.show();
                                let _ = win.set_focus();
                            }
                        }
                        "pause_15m" => {
                            let _ = app_handle.emit("desksense://tray-action", "pause_15m");
                        }
                        "pause_1h" => {
                            let _ = app_handle.emit("desksense://tray-action", "pause_1h");
                        }
                        "resume" => {
                            let _ = app_handle.emit("desksense://tray-action", "resume");
                        }
                        "recalibrate" => {
                            if let Some(win) = app_handle.get_webview_window("main") {
                                let _ = win.show();
                                let _ = win.set_focus();
                            }
                            let _ = app_handle.emit("desksense://tray-action", "recalibrate");
                        }
                        "settings" => {
                            if let Some(win) = app_handle.get_webview_window("main") {
                                let _ = win.show();
                                let _ = win.set_focus();
                            }
                            let _ = app_handle.emit("desksense://tray-action", "settings");
                        }
                        "quit" => {
                            app_handle.exit(0);
                        }
                        _ => {}
                    }
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                })
                .build(app)?;

            // Register Global Hotkey Ctrl+Shift+P (P3-04)
            let shortcut: Shortcut = "Ctrl+Shift+P".parse().unwrap();
            let app_handle_hotkey = app.handle().clone();
            app.global_shortcut().on_shortcut(shortcut, move |_app, _shortcut, _event| {
                let _ = app_handle_hotkey.emit("desksense://hotkey-toggle", ());
            })?;

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running DeskSense tauri application");
}
