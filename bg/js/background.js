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

port.onMessage.addListener((data) => {
    if (data.command === 'get_tabs') {
        getTabs((tabs) => {
            port.postMessage(tabs);
        })
    } else if (data.command === 'focus_tab') {
        focusTab(data.data);
    }
});
