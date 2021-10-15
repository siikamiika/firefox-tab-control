function getFocusedWindow(callback) {
    function onError(error) {
        console.log(`Error: ${error}`);
    }

    var querying = browser.windows.getLastFocused({});
    querying.then(callback, onError);
}

function getTabs(callback) {
    function onError(error) {
        console.log(`Error: ${error}`);
    }

    var querying = browser.tabs.query({});
    querying.then(callback, onError);
}

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

var port = browser.runtime.connectNative("tab_control");

port.onMessage.addListener(async (data) => {
    if (data.command === 'get_focused_window') {
        getFocusedWindow((focusedWindow) => {
            port.postMessage(focusedWindow);
        })
    } else if (data.command === 'get_tabs') {
        getTabs((tabs) => {
            port.postMessage(tabs);
        })
    } else if (data.command === 'focus_tab') {
        const tab = data.data;
        const previousPreface = await guessPreviousPreface(tab);
        await browser.windows.update(tab.windowId, {titlePreface: `focus_window_id:${tab.windowId} `});
        focusTab(data.data);
        port.postMessage({ok: true});
        setTimeout(
            () => browser.windows.update(tab.windowId, {titlePreface: previousPreface}),
            1000
        );
    }
});
