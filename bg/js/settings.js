function getTabs(callback) {
    function onError(error) {
        console.log(`Error: ${error}`);
    }

    var querying = browser.tabs.query({});
    querying.then(callback, onError);
}

function showPrettyJson(object) {
    let tabsAsJson = JSON.stringify(object, null, 4);
    let show = document.createElement('pre');
    show.innerText = ''+tabsAsJson.length +'\n'+tabsAsJson;
    document.body.appendChild(show);
}

////
getTabs(showPrettyJson);
