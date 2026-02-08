// Anti-bot stealth overrides for Playwright MCP.
// Injected via browser.initScript to run before any page scripts.
// Covers the most common headless browser detection vectors.

(() => {
    "use strict";

    // 1. Remove the #1 bot signal: navigator.webdriver
    Object.defineProperty(navigator, "webdriver", {
        get: () => undefined,
        configurable: true,
    });

    // 2. Override navigator.plugins to report realistic Chrome plugins
    Object.defineProperty(navigator, "plugins", {
        get: () => {
            const fakePlugins = [
                {
                    name: "Chrome PDF Plugin",
                    filename: "internal-pdf-viewer",
                    description: "Portable Document Format",
                    length: 1,
                },
                {
                    name: "Chrome PDF Viewer",
                    filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai",
                    description: "",
                    length: 1,
                },
                {
                    name: "Native Client",
                    filename: "internal-nacl-plugin",
                    description: "",
                    length: 2,
                },
            ];
            // Make it look like a PluginArray
            fakePlugins.item = (i) => fakePlugins[i] || null;
            fakePlugins.namedItem = (name) =>
                fakePlugins.find((p) => p.name === name) || null;
            fakePlugins.refresh = () => { };
            return fakePlugins;
        },
        configurable: true,
    });

    // 3. Override navigator.languages to report realistic set
    Object.defineProperty(navigator, "languages", {
        get: () => ["en-US", "en"],
        configurable: true,
    });

    // 4. Override navigator.platform to match common User-Agent
    Object.defineProperty(navigator, "platform", {
        get: () => {
            const ua = navigator.userAgent || "";
            if (ua.includes("Mac")) return "MacIntel";
            if (ua.includes("Win")) return "Win32";
            if (ua.includes("Linux")) return "Linux x86_64";
            return "MacIntel"; // default
        },
        configurable: true,
    });

    // 5. Patch chrome.runtime to look like a real Chrome install
    if (!window.chrome) {
        window.chrome = {};
    }
    if (!window.chrome.runtime) {
        window.chrome.runtime = {
            connect: () => { },
            sendMessage: () => { },
            id: undefined,
        };
    }

    // 6. Override WebGL vendor/renderer strings to avoid fingerprint mismatches
    const getParameterProto = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function (param) {
        // UNMASKED_VENDOR_WEBGL
        if (param === 0x9245) return "Intel Inc.";
        // UNMASKED_RENDERER_WEBGL
        if (param === 0x9246) return "Intel Iris OpenGL Engine";
        return getParameterProto.call(this, param);
    };

    // Also patch WebGL2
    if (typeof WebGL2RenderingContext !== "undefined") {
        const getParameter2Proto = WebGL2RenderingContext.prototype.getParameter;
        WebGL2RenderingContext.prototype.getParameter = function (param) {
            if (param === 0x9245) return "Intel Inc.";
            if (param === 0x9246) return "Intel Iris OpenGL Engine";
            return getParameter2Proto.call(this, param);
        };
    }

    // 7. Patch Permissions.prototype.query to report correct notification status
    const originalQuery = Permissions.prototype.query;
    Permissions.prototype.query = function (params) {
        if (params && params.name === "notifications") {
            return Promise.resolve({ state: Notification.permission });
        }
        return originalQuery.call(this, params);
    };

    // 8. Patch navigator.connection to look real
    if (!navigator.connection) {
        Object.defineProperty(navigator, "connection", {
            get: () => ({
                effectiveType: "4g",
                rtt: 50,
                downlink: 10,
                saveData: false,
            }),
            configurable: true,
        });
    }

    // 9. Ensure navigator.hardwareConcurrency returns a realistic value
    Object.defineProperty(navigator, "hardwareConcurrency", {
        get: () => 8,
        configurable: true,
    });

    // 10. Ensure navigator.deviceMemory returns a realistic value
    Object.defineProperty(navigator, "deviceMemory", {
        get: () => 8,
        configurable: true,
    });
})();
