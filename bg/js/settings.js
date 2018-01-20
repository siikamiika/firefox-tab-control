function getTabs(callback) {
    function onError(error) {
        console.log(`Error: ${error}`);
    }

    var querying = browser.tabs.query({});
    querying.then(callback, onError);
}

function showPrettyJson(object) {
    let asJSON = JSON.stringify(object, null, 4);
    let show = document.createElement('pre');
    show.innerText = asJSON;
    document.body.appendChild(show);
}

function getFocusedWindow(callback) {
    function onError(error) {
        console.log(`Error: ${error}`);
    }

    var querying = browser.windows.getLastFocused({});
    querying.then(callback, onError);
}

////
// getTabs(showPrettyJson);
getFocusedWindow(showPrettyJson);
