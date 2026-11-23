import Cocoa
import WebKit

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate {
    private var window: NSWindow!
    private var webView: WKWebView!
    private var serverProcess: Process?
    private let baseURL = URL(string: "http://127.0.0.1:18493")!
    private let healthURL = URL(string: "http://127.0.0.1:18493/api/health")!

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        NSApp.appearance = NSAppearance(named: .darkAqua)

        setupMenus()
        setupWindow()
        ensureBackendAndLoad()

        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return true
    }

    func applicationWillTerminate(_ notification: Notification) {
        if let proc = serverProcess, proc.isRunning {
            proc.terminate()
            proc.waitUntilExit()
        }
    }

    private func setupMenus() {
        let mainMenu = NSMenu()
        let appMenuItem = NSMenuItem()
        mainMenu.addItem(appMenuItem)
        let appMenu = NSMenu(title: "Redragon K653 Control")
        appMenuItem.submenu = appMenu

        appMenu.addItem(
            NSMenuItem(
                title: "Sobre Redragon K653 Control",
                action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)),
                keyEquivalent: ""
            )
        )
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(NSMenuItem(title: "Recarregar", action: #selector(reloadWebView(_:)), keyEquivalent: "r"))
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(NSMenuItem(title: "Sair", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"))

        NSApp.mainMenu = mainMenu
    }

    private func setupWindow() {
        let size = NSSize(width: 1220, height: 840)
        window = NSWindow(
            contentRect: NSRect(origin: .zero, size: size),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "Redragon K653 Control"
        window.minSize = NSSize(width: 900, height: 640)
        window.backgroundColor = NSColor(calibratedRed: 0.043, green: 0.051, blue: 0.071, alpha: 1.0)
        window.center()

        let config = WKWebViewConfiguration()
        webView = WKWebView(frame: window.contentView?.bounds ?? .zero, configuration: config)
        webView.autoresizingMask = [.width, .height]
        webView.navigationDelegate = self
        webView.setValue(false, forKey: "drawsBackground")

        let loadingHTML = """
        <html><body style="background:#0b0d12;color:#eef2ff;font-family:-apple-system,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
        <div style="text-align:center;">
          <div style="font-size:18px;font-weight:700;margin-bottom:8px;">Redragon K653 Control</div>
          <div style="font-size:13px;color:#93a1be;">Carregando painel do teclado...</div>
        </div></body></html>
        """
        webView.loadHTMLString(loadingHTML, baseURL: nil)

        window.contentView = webView
        window.makeKeyAndOrderFront(nil)
    }

    @objc private func reloadWebView(_ sender: Any?) {
        webView.load(URLRequest(url: baseURL))
    }

    private func resolveServerScript() -> URL? {
        if let resURL = Bundle.main.resourceURL {
            let bundled = resURL.appendingPathComponent("backend/server.py")
            if FileManager.default.fileExists(atPath: bundled.path) {
                return bundled
            }
        }
        let fallback = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent("server.py")
        if FileManager.default.fileExists(atPath: fallback.path) {
            return fallback
        }
        return nil
    }

    private func checkHealth(completion: @escaping (Bool) -> Void) {
        var req = URLRequest(url: healthURL)
        req.timeoutInterval = 0.4
        URLSession.shared.dataTask(with: req) { data, resp, _ in
            let ok = (resp as? HTTPURLResponse)?.statusCode == 200 && data != nil
            completion(ok)
        }.resume()
    }

    private func ensureBackendAndLoad() {
        checkHealth { [weak self] alreadyUp in
            guard let self = self else { return }
            if alreadyUp {
                DispatchQueue.main.async { self.webView.load(URLRequest(url: self.baseURL)) }
                return
            }
            DispatchQueue.global(qos: .userInitiated).async {
                guard let serverScript = self.resolveServerScript() else { return }
                let proc = Process()
                proc.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
                proc.arguments = [serverScript.path]
                proc.currentDirectoryURL = serverScript.deletingLastPathComponent()

                let logURL = URL(fileURLWithPath: "/tmp/redragon_k653_mac_app.log")
                FileManager.default.createFile(atPath: logURL.path, contents: nil)
                if let logHandle = try? FileHandle(forWritingTo: logURL) {
                    proc.standardOutput = logHandle
                    proc.standardError = logHandle
                }
                do {
                    try proc.run()
                    self.serverProcess = proc
                } catch {
                    return
                }
                self.pollUntilReady(attemptsLeft: 40)
            }
        }
    }

    private func pollUntilReady(attemptsLeft: Int) {
        checkHealth { [weak self] ok in
            guard let self = self else { return }
            if ok {
                DispatchQueue.main.async { self.webView.load(URLRequest(url: self.baseURL)) }
                return
            }
            if attemptsLeft <= 1 { return }
            DispatchQueue.global(qos: .userInitiated).asyncAfter(deadline: .now() + 0.1) {
                self.pollUntilReady(attemptsLeft: attemptsLeft - 1)
            }
        }
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
