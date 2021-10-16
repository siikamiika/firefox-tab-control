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
        this._previousPrefaceCache = {};
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
        this._server.setCommandHandler('notify_window_focused', this._onNotifyWindowFocused.bind(this));
    }

    async _onGetFocusedWindow() {
        return await browser.windows.getLastFocused({});
    }

    async _onGetTabs() {
        return await browser.tabs.query({});
    }

    async _onFocusTab({id, args: {windowId, tabId, randomPrefix}}) {
        const previousPreface = await this._guessPreviousPreface(windowId);
        this._previousPrefaceCache[id] = previousPreface;
        await browser.windows.update(windowId, {titlePreface: `${previousPreface}${randomPrefix}:${windowId} `});
        browser.windows.update(windowId, {focused: true});
        browser.tabs.update(tabId, {active: true});
        return {ok: true};
    }

    async _onNotifyWindowFocused({args: {id, windowId}}) {
        const titlePreface = this._previousPrefaceCache[id];
        if (typeof titlePreface === 'undefined') { return; }
        delete this._previousPrefaceCache[id];
        browser.windows.update(windowId, {titlePreface});
    }

    async _guessPreviousPreface(windowId) {
        const {title: tabTitle} = (await browser.tabs.query({windowId, active: true}))[0];
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
