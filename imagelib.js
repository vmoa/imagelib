//
// Javascript for RFO Image Library
//

var color_selected     = '#ffbbba';
var color_unselected   = 'gray';

var black        = 'black';
var yellow       = 'yellow';
var green        = '#08FF08';
var light_green  = '#C0FFC0';
var red          = '#FF0808';

/* Global so keydownHandler can access */
var previewElement = 0;

/* Mode: 0=none, 1=all, -1=toggle */
function select(el, mode) {
    console.log("select("+el+","+mode+")");
    var element = document.getElementById(el);
    if (mode == -1) {
        element.rfoIsSelected = ! element.rfoIsSelected;
    } else {
        element.rfoIsSelected = mode;  /* Ain't that convenient */
    }
    element.style.borderColor = element.rfoIsSelected ? color_selected : color_unselected;
}

function toggle(el) {
    select(el, -1);
}

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

function basename(path) {
   return path.split('/').reverse()[0];
}

function keydownHandler(event) {
    console.log("keydownHandler(" + event + ")");
    if (document.getElementById("preview-container").style.display == "block") {
        if (event.keyCode === 27) {  // <ESC> keycode
            closePreview();
        } else if (event.keyCode === 32) {  // <SPACE> keycode
            toggleSelect(previewElement, -1);
        }
    }
}

function preview(el) {
    console.log("preview("+el+")");
    previewElement = el;  /* make available to event handler */
    var image = document.getElementById(el+'img');
    var previewWindow = document.getElementById("preview-window");
    var previewImg = document.getElementById("preview-img");
    previewImg.src = image.src;
    previewImg.maxWidth = previewWindow.clientWidth;
    previewImg.maxHeight = previewWindow.clientHeight;
    document.getElementById('preview-filename').innerHTML = basename(image.src);
    document.getElementById("preview-content").style.borderColor = document.getElementById(el).rfoIsSelected ? color_selected : color_unselected;
    document.getElementById("preview-select").setAttribute("onclick","toggleSelect('" + el + "',-1)")
    document.addEventListener("keydown", keydownHandler);
    document.getElementById("preview-container").style.display = "block";
}

function toggleSelect(el) {
    select(el, -1);
    document.getElementById("preview-content").style.borderColor = document.getElementById(el).rfoIsSelected ? color_selected : color_unselected;
}

function closePreview() {
    document.getElementById("preview-container").style.display = "none";
    document.removeEventListener("keydown", keydownHandler);
}
