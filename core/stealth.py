"""
Stealth script — injected into every Playwright browser context to hide automation.
Single source of truth: every module imports from here.

Now dynamic: generates JavaScript that matches the account's Android device fingerprint
so Instagram sees consistent device identity across browser and API sessions.
"""


def get_stealth_script(fingerprint=None):
    """
    Build a stealth injection script tailored to the account's fingerprint.

    Args:
        fingerprint: dict from generate_browser_fingerprint().
                     If None, uses sensible Android defaults.

    Returns:
        str: JavaScript to inject via context.add_init_script()
    """
    if fingerprint is None:
        webgl_vendor = "Qualcomm"
        webgl_renderer = "Adreno (TM) 740"
        platform = "Linux armv8l"
    else:
        webgl = fingerprint.get("webgl", {})
        webgl_vendor = webgl.get("vendor", "Qualcomm")
        webgl_renderer = webgl.get("renderer", "Adreno (TM) 740")
        platform = fingerprint.get("platform", "Linux armv8l")

    webgl_vendor_js = webgl_vendor.replace("'", "\\'")
    webgl_renderer_js = webgl_renderer.replace("'", "\\'")
    platform_js = platform.replace("'", "\\'")

    return f"""
    // ── Hide automation signals ──
    Object.defineProperty(navigator, 'webdriver', {{ get: () => false }});

    // ── Platform: match Android device ──
    Object.defineProperty(navigator, 'platform', {{ get: () => '{platform_js}' }});

    // ── Chrome on Android: no plugins exposed ──
    Object.defineProperty(navigator, 'plugins', {{
        get: () => {{
            const arr = [];
            arr.length = 0;
            return arr;
        }}
    }});

    // ── Languages ──
    Object.defineProperty(navigator, 'languages', {{ get: () => ['en-US', 'en'] }});

    // ── Chrome runtime object (present in real Chrome) ──
    if (!window.chrome) {{
        window.chrome = {{ runtime: {{}} }};
    }}

    // ── Hardware concurrency: realistic for mobile (4-8 cores) ──
    Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => {4 if 'MC4' in webgl_renderer else 8} }});

    // ── Device memory: realistic for flagship Android (6-8 GB) ──
    Object.defineProperty(navigator, 'deviceMemory', {{ get: () => {6 if 'MC4' in webgl_renderer else 8} }});

    // ── Max touch points: Android Chrome = 5 ──
    Object.defineProperty(navigator, 'maxTouchPoints', {{ get: () => 5 }});

    // ── Connection API: realistic 4G/5G ──
    if (navigator.connection) {{
        Object.defineProperty(navigator.connection, 'effectiveType', {{ get: () => '4g' }});
    }}

    // ── Permissions: behave like real Chrome ──
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications'
            ? Promise.resolve({{ state: Notification.permission }})
            : originalQuery(parameters)
    );

    // ── WebGL: spoof GPU to match the Android device's actual GPU ──
    const _getParameterWebGL1 = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(param) {{
        if (param === 37445) return '{webgl_vendor_js}';
        if (param === 37446) return '{webgl_renderer_js}';
        return _getParameterWebGL1.call(this, param);
    }};

    // WebGL2 as well (Chrome uses WebGL2 by default)
    if (typeof WebGL2RenderingContext !== 'undefined') {{
        const _getParameterWebGL2 = WebGL2RenderingContext.prototype.getParameter;
        WebGL2RenderingContext.prototype.getParameter = function(param) {{
            if (param === 37445) return '{webgl_vendor_js}';
            if (param === 37446) return '{webgl_renderer_js}';
            return _getParameterWebGL2.call(this, param);
        }};
    }}

    // ── Media devices: return empty (no camera/mic exposed in mobile Chrome) ──
    if (navigator.mediaDevices) {{
        Object.defineProperty(navigator.mediaDevices, 'enumerateDevices', {{
            value: async () => []
        }});
    }}

    // ── Remove phantom/selenium artifacts ──
    delete window.callPhantom;
    delete window.__phantom;
    delete window.__selenium_unwrapped;
    delete window.__driver_evaluate;
    delete window.__webdriver_evaluate;
    delete window.__fxdriver_evaluate;
    delete window.__driver_unwrapped;
    delete window.__webdriver_unwrapped;
    delete window.__fxdriver_unwrapped;
    delete window.__webdriver_script_fn;
    delete document.__webdriver_evaluate;
    delete document.__selenium_evaluate;
    delete document.__fxdriver_evaluate;
    delete document.__driver_evaluate;
"""


# Backwards-compatible constant for any code that still imports STEALTH_SCRIPT
STEALTH_SCRIPT = get_stealth_script()
