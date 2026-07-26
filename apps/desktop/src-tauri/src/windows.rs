// Windows taskbar icon fix.
//
// Tauri v2's `window.set_icon()` only sets ICON_SMALL (titlebar). The
// taskbar uses ICON_BIG, which Tauri never sets. In dev mode
// (bundle.active=false) the icon isn't even embedded in the exe, so the
// taskbar falls back to a generic/default icon.
//
// This module loads the icon from file at runtime and sets BOTH ICON_SMALL
// and ICON_BIG via the Win32 WM_SETICON message, following the workaround
// in https://github.com/62mi/filer/pull/105.

use std::path::PathBuf;
use std::ptr;

use windows_sys::Win32::Foundation::HWND;
use windows_sys::Win32::UI::WindowsAndMessaging::{
    LoadImageW, SendMessageW, ICON_BIG, ICON_SMALL, IMAGE_ICON, LR_DEFAULTSIZE, LR_LOADFROMFILE,
    LR_SHARED, WM_SETICON,
};

/// Path to the .ico file relative to the crate root.
fn icon_path() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("icons").join("icon.ico")
}

/// Convert a Rust string to a null-terminated UTF-16 vector for Win32 APIs.
fn to_wide(s: &str) -> Vec<u16> {
    s.encode_utf16().chain(std::iter::once(0)).collect()
}

/// Load an icon from a file path using LoadImageW and set it as both
/// ICON_SMALL (titlebar) and ICON_BIG (taskbar) on the given window.
pub fn apply_taskbar_icon(hwnd: HWND) {
    let path = icon_path();
    let path_wide = to_wide(&path.to_string_lossy());

    // LoadImageW with LR_SHARED returns a shared handle managed by the system,
    // so we don't need to call DestroyIcon.
    let hicon = unsafe {
        LoadImageW(
            ptr::null_mut(),           // hInstance (null = load from file)
            path_wide.as_ptr(),        // lpName (file path)
            IMAGE_ICON,                // uType
            0,                         // cx (0 = default)
            0,                         // cy (0 = default)
            LR_LOADFROMFILE | LR_SHARED | LR_DEFAULTSIZE,
        )
    };

    if hicon.is_null() {
        eprintln!(
            "[windows] Failed to load icon from {:?} (error {})",
            path,
            unsafe { windows_sys::Win32::Foundation::GetLastError() }
        );
        return;
    }

    unsafe {
        SendMessageW(hwnd, WM_SETICON, ICON_SMALL as usize, hicon as isize);
        SendMessageW(hwnd, WM_SETICON, ICON_BIG as usize, hicon as isize);
    }

    eprintln!("[windows] Taskbar icon applied from {:?}", path);
}
