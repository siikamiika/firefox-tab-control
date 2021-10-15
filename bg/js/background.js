class NativeMessagingServer {
    constructor(name) {
        this._name = name;
        this._port = null;
        this._command_handlers = {};
    }

    start() {
        this._port = browser.runtime.connectNative(this._name);
        this._port.onMessage.addListener(this._onMessage.bind(this));
    }

    setCommandHandler(name, cb) {
        this._command_handlers[name] = cb;
    }

    async _onMessage(data) {
        const handler = this._command_handlers[data.command];
        if (!handler) { return; }
        const results = await handler(data);
        this._port.postMessage({id: data.id, results});
    }
}

class TabControlBackend {
    constructor() {
        this._server = null;
    }

    start() {
        this._server = new NativeMessagingServer('tab_control');
        this._setHandlers();
        this._server.start();
    }

    _setHandlers() {
        this._server.setCommandHandler('get_focused_window', this._onGetFocusedWindow.bind(this));
        this._server.setCommandHandler('get_tabs', this._onGetTabs.bind(this));
        this._server.setCommandHandler('focus_tab', this._onFocusTab.bind(this));
    }

    async _onGetFocusedWindow() {
        return await browser.windows.getLastFocused({});
    }

    async _onGetTabs() {
        return await browser.tabs.query({});
    }

    async _onFocusTab({args: {tab}}) {
        const previousPreface = await this._guessPreviousPreface(tab);
        await browser.windows.update(tab.windowId, {titlePreface: `focus_window_id:${tab.windowId} `});
        this._focusTab(tab);
        setTimeout(
            () => browser.windows.update(tab.windowId, {titlePreface: previousPreface}),
            1000
        );
        return {ok: true};
    }

    _focusTab(tab) {
        browser.windows.update(tab.windowId, {focused: true});
        browser.tabs.update(tab.id, {active: true});
    }

    async _guessPreviousPreface(tab) {
        const {windowId, title: tabTitle} = tab;
        const {title: windowTitle} = await browser.windows.get(windowId);
        let tabNameStart = windowTitle.indexOf(tabTitle);
        if (tabNameStart < 0) {
            tabNameStart = 0;
        }
        return windowTitle.substr(0, tabNameStart);
    }
}

const backend = new TabControlBackend();
backend.start();
