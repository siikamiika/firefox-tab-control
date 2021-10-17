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
        this._titlePrefaceCache = {};
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
        this._server.setCommandHandler('show_window_id_in_title', this._onShowWindowIdInTitle.bind(this));
        this._server.setCommandHandler('remove_window_id_from_title', this._onRemoveWindowIdFromTitle.bind(this));
    }

    async _onGetFocusedWindow() {
        return await browser.windows.getLastFocused({});
    }

    async _onGetTabs() {
        return await browser.tabs.query({});
    }

    async _onFocusTab({args: {tab}}) {
        browser.windows.update(tab.windowId, {focused: true});
        browser.tabs.update(tab.id, {active: true});
        return {ok: true};
    }

    async _onShowWindowIdInTitle({args: {windowId}}) {
        if (this._titlePrefaceCache[windowId]) {
            const {previousPreface, identifier} = this._titlePrefaceCache[windowId];
            await browser.windows.update(windowId, {titlePreface: `${previousPreface}${identifier} `});
            return {identifier};
        }
        const randomString = Array.from(crypto.getRandomValues(new Uint8Array(16)))
            .map((v) => v.toString(16).padStart(2, '0'))
            .join('');
        const identifier = `${randomString}:${windowId}`;
        let previousPreface = await this._guessPreviousPreface(windowId);
        // some other call got here first, give up
        if (this._titlePrefaceCache[windowId]) {
            return {identifier: null};
        }
        this._titlePrefaceCache[windowId] = {previousPreface, identifier};
        await browser.windows.update(windowId, {titlePreface: `${previousPreface}${identifier} `});
        return {identifier};
    }

    async _onRemoveWindowIdFromTitle({args: {windowId}}) {
        if (this._titlePrefaceCache[windowId]) {
            const {previousPreface} = this._titlePrefaceCache[windowId];
            await browser.windows.update(windowId, {titlePreface: previousPreface});
            delete this._titlePrefaceCache[windowId];
        }
        return {ok: true};
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
