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
        await browser.windows.update(data.data.windowId, {titlePreface: `focus_window_id:${data.data.windowId} `});
        focusTab(data.data);
    }
});
