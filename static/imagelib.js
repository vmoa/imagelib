//
// Javascript for RFO Image Library
//

var color_selected     = '#ffbbba';
var color_unselected   = 'gray';
var color_downloading  = 'orange';

/* Element that is currently being previewed (global so that keydownHandler() can access) */
var previewElement = 0;

/* Initialize awesomeplete dropdowns (https://projects.verou.me/awesomplete/) */
document.addEventListener("DOMContentLoaded", function() {
    new Awesomplete(document.getElementById("awesomeDate"), {
        list: "#datelist",
        filter: function (text, input) {  /* Constrains match to start of item */
            return text.indexOf(input) === 0;
        },
        maxItems: 25,
        minChars: 1,
        sort: false,  /* Preserve sort order we set with SQLite */
    });
    new Awesomplete(document.getElementById("awesomeTarget"), {
        list: "#targetlist",
        maxItems: 25,
        minChars: 1,
    });
});


/* Set `rfoIsSelected` attribute based on mode: 0=none, 1=all, -1=toggle */
function select(el, mode) {
    /* console.log("select("+el+","+mode+")"); */
    var element = document.getElementById(el);
    if (mode == -1) {
        element.rfoIsSelected = ! element.rfoIsSelected;
    } else {
        element.rfoIsSelected = mode;  /* Ain't that convenient */
    }
    element.style.borderColor = element.rfoIsSelected ? color_selected : color_unselected;
}

/* Called from html via onclick() for thumbnail title */
function toggle(el) {
    select(el, -1);
}

/* Call select() for each element whose id starts with `prefix`; see select() for `mode` */
function selectMulti(prefix, mode) {
    console.log("selectMulti("+prefix+","+mode+")");
    var len = prefix.length;
    var thumbs = document.getElementsByClassName('thumb');
    for (let i=0; i < thumbs.length; i++) {
        if (thumbs[i].id.substring(0,len) == prefix) {
            select(thumbs[i].id, mode);
        }
    }
}

/* Time delayed callback to reset selection colors after download (see setRecids()) */
function recolorSelect() {
    console.log("recolorSelect()");
    var thumbs = document.getElementsByClassName('thumb');
    for (let i=0; i < thumbs.length; i++) {
        thumbs[i].style.borderColor = thumbs[i].rfoIsSelected ? color_selected : color_unselected;
    }
}

/* Onclick() function for download button: fill in the `recids` form field based on `rfoIsSelected` before submitting form */
function setRecids() {
    console.log("setRecids()");
    var dlist = [];
    var thumbs = document.getElementsByClassName('thumb');
    for (let i=0; i < thumbs.length; i++) {
        if (thumbs[i].rfoIsSelected) {
            dlist.push(thumbs[i].dataset.recid);
            thumbs[i].rfoIsSelected = 0;
            thumbs[i].style.borderColor = color_downloading;
        }
    }
    console.log("recids=" + dlist.join(","));
    document.dlform.recids.value = dlist.join(",");
    setTimeout(recolorSelect, 2000)
}

/* Reutrn just the filename component of a full path */
function basename(path) {
   return path.split('/').reverse()[0];
}

/* Accept several keystrokes in our preview modal */
function keydownHandler(event) {
    console.log("keydownHandler(" + event + ")");
    if (document.getElementById("preview-container").style.display == "block") {
        if (event.keyCode === 27) {  // <ESC> keycode
            closePreview();
        } else if (event.keyCode === 32) {  // <SPACE> keycode
            toggleSelect(previewElement, -1);
        }
    }
    if (document.getElementById("help-container").style.display == "block") {
        if (event.keyCode === 27) {  // <ESC> keycode
            closeHelp();
        }
    }
}

/* Preview modal: overlays current display with preview png */
function preview(el) {
    console.log("preview("+el+")");
    previewElement = el;  /* make available to event handler */
    var recid = document.getElementById(el).dataset.recid;
    var image = document.getElementById(el+'img');
    var previewWindow = document.getElementById("preview-window");
    var previewImg = document.getElementById("preview-img");
    var preview_src = image.src.replace("-thumb.png", ".png")

    /* Paint our image */
    previewImg.src = preview_src
    previewImg.maxWidth = previewWindow.clientWidth;
    previewImg.maxHeight = previewWindow.clientHeight;
    document.getElementById('preview-filename').innerHTML = basename(preview_src).replaceAll("%20", " ");
    document.getElementById("preview-content").style.borderColor = document.getElementById(el).rfoIsSelected ? color_selected : color_unselected;

    /* Fetch the deets, with a callback to paint them */
    var xhttp = new XMLHttpRequest();
    xhttp.onreadystatechange = function() {
        if (this.readyState == 4 && this.status == 200) {
            console.log("rendering deets")
            document.getElementById("preview-deets").innerHTML = xhttp.responseText;
        }
    };
    xhttp.open("GET", "/deets?recid="+recid, true);
    console.log("fetching /deets?recid="+recid);
    xhttp.send();

    /* Enable keyboard shortcuts */
    document.getElementById("preview-select").setAttribute("onclick","toggleSelect('" + el + "',-1)")
    document.addEventListener("keydown", keydownHandler);
    document.getElementById("preview-container").style.display = "block";
}

/* Special flavor of toggle() that also colors the preview border */
function toggleSelect(el) {
    select(el, -1);
    document.getElementById("preview-content").style.borderColor = document.getElementById(el).rfoIsSelected ? color_selected : color_unselected;
}

/* Close the preview modal and return to our regularly scheduled display */
function closePreview() {
    document.getElementById("preview-container").style.display = "none";
    document.removeEventListener("keydown", keydownHandler);
}

/* Help modal: overlays current display with help text */
function help() {
    console.log("help()");
    var xhttp = new XMLHttpRequest();
    xhttp.onreadystatechange = function() {
        if (this.readyState == 4 && this.status == 200) {
            console.log("rendering help text")
            document.getElementById("help-html").innerHTML = xhttp.responseText;
        }
    };
    xhttp.open("GET", "static/help.html", true);
    console.log("fetching static/help.hmtl");
    xhttp.send();
    document.addEventListener("keydown", keydownHandler);
    document.getElementById("help-container").style.display = "block";
}

/* Close the help modal and return to our regularly scheduled display */
function closeHelp() {
    document.getElementById("help-container").style.display = "none";
    document.removeEventListener("keydown", keydownHandler);
}
