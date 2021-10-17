class NativeMessagingServer {
    constructor(name) {
        this._name = name;
        this._port = null;
        this._handlers = {};
    }

    start() {
        this._port = browser.runtime.connectNative(this._name);
        this._port.onMessage.addListener(this._onMessage.bind(this));
    }

    setCommandHandler(name, handler) {
        this._handlers[name] = {type: 'command', handler};
    }

    setSubscribeHandler(name, handler) {
        this._handlers[name] = {type: 'subscribe', handler};
    }

    async _onMessage(data) {
        if (!this._handlers[data.command]) { return; }
        const {type, handler} = this._handlers[data.command];
        if (type === 'command') {
            const results = await handler(data);
            this._port.postMessage({id: data.id, type: 'results', results});
        } else if (type === 'subscribe') {
            const postMessageChannel = (results) => this._port.postMessage({id: data.id, type: 'update', results});
            handler(data, postMessageChannel);
        }
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
        // commands
        this._server.setCommandHandler('get_windows', this._onGetWindows.bind(this));
        this._server.setCommandHandler('get_tabs', this._onGetTabs.bind(this));
        this._server.setCommandHandler('focus_tab', this._onFocusTab.bind(this));
        this._server.setCommandHandler('identify_window', this._onIdentifyWindow.bind(this));
        // subscriptions
        this._server.setSubscribeHandler('subscribe_new_window', this._onSubscribeNewWindow.bind(this));
        this._server.setSubscribeHandler('subscribe_close_window', this._onSubscribeCloseWindow.bind(this));
    }

    async _onGetWindows() {
        return await browser.windows.getAll();
    }

    async _onGetTabs() {
        return await browser.tabs.query({});
    }

    async _onFocusTab({args: {tab}}) {
        browser.windows.update(tab.windowId, {focused: true});
        browser.tabs.update(tab.id, {active: true});
        return {ok: true};
    }

    async _onIdentifyWindow({args: {windowId, on}}) {
        // off
        if (!on) {
            if (this._titlePrefaceCache[windowId]) {
                const {previousPreface} = this._titlePrefaceCache[windowId];
                await browser.windows.update(windowId, {titlePreface: previousPreface});
                delete this._titlePrefaceCache[windowId];
            }
            return {identifier: null};
        }
        // on
        if (this._titlePrefaceCache[windowId]) {
            const {previousPreface, identifier} = this._titlePrefaceCache[windowId];
            await browser.windows.update(windowId, {titlePreface: `${previousPreface}${identifier} `});
            return {identifier};
        }
        const identifier = Array.from(crypto.getRandomValues(new Uint8Array(16)))
            .map((v) => v.toString(16).padStart(2, '0'))
            .join('');
        let previousPreface = await this._guessPreviousPreface(windowId);
        // some other call got here first, give up
        if (this._titlePrefaceCache[windowId]) {
            return {identifier: null};
        }
        this._titlePrefaceCache[windowId] = {previousPreface, identifier};
        await browser.windows.update(windowId, {titlePreface: `${previousPreface}${identifier} `});
        return {identifier};
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

    _onSubscribeNewWindow(_, postMessageChannel) {
        browser.windows.onCreated.addListener(postMessageChannel);
    }

    _onSubscribeCloseWindow(_, postMessageChannel) {
        browser.windows.onRemoved.addListener((id) => postMessageChannel({id}));
    }
}

const backend = new TabControlBackend();
backend.start();
