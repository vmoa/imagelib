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

/* Mode: 0=none, 1=all, -1=toggle */
function select(el, mode) {
    console.log("select("+el+","+mode+")");
    var element = document.getElementById(el);
    if (mode == -1) {
        element.rfoIsSelected = ! element.rfoIsSelected;
    } else {
        element.rfoIsSelected = mode;  /* Ain't that convenient */
    }
    if (element.rfoIsSelected) {
        element.style.borderColor = color_selected;
    } else {
        element.style.borderColor = color_unselected;
    }
}

function toggle(el) {
    select(el, -1);
}

function selectMulti(prefix, mode) {
    console.log("selectMulti("+prefix+","+mode+")");
    var allThumbs = document.getElementsByClassName('thumb');
    for (let i=0; i < allThumbs.length; i++) {
        /* TODO: filter on prefix */
        select(allThumbs[i].id, mode);
    }
}

function basename(path) {
   return path.split('/').reverse()[0];
}

function preview(el) {
    console.log("preview("+el+")");
    var image = document.getElementById(el+'img');
    var previewWindow = document.getElementById("preview-window");
    var previewImg = document.getElementById("preview-img");
    previewImg.src = image.src;
    previewImg.maxWidth = previewWindow.clientWidth;
    previewImg.maxHeight = previewWindow.clientHeight;
    document.getElementById('preview-filename').innerHTML = basename(image.src);
    document.getElementById("preview-container").style.display = "block";
}

function closePreview() {
    document.getElementById("preview-container").style.display = "none";
}
