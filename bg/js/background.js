function focusTab(tab) {
    browser.windows.update(tab.windowId, {focused: true});
    browser.tabs.update(tab.id, {active: true});
}

async function guessPreviousPreface(tab) {
    const {windowId, title: tabTitle} = tab;
    const {title: windowTitle} = await browser.windows.get(windowId);
    let tabNameStart = windowTitle.indexOf(tabTitle);
    if (tabNameStart < 0) {
        tabNameStart = 0;
    }
    return windowTitle.substr(0, tabNameStart);
}

// -------------------------------------------------------

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

const server = new NativeMessagingServer('tab_control');
server.setCommandHandler('get_focused_window', async () => {
    return await browser.windows.getLastFocused({});
});
server.setCommandHandler('get_tabs', async () => {
    return await browser.tabs.query({});
});
server.setCommandHandler('focus_tab', async ({args: {tab}}) => {
    const previousPreface = await guessPreviousPreface(tab);
    await browser.windows.update(tab.windowId, {titlePreface: `focus_window_id:${tab.windowId} `});
    focusTab(tab);
    setTimeout(
        () => browser.windows.update(tab.windowId, {titlePreface: previousPreface}),
        1000
    );
    return {ok: true};
});
server.start();
