// written by Dean Edwards, 2006
// http://dean.edwards.name/weblog/2006/03/faster

Behaviour._apply = Behaviour.apply;
Behaviour.apply = function() {
	if (this.applied) return;
	this.applied = true;
	this._apply();
};
if (document.addEventListener) {
	document.addEventListener("DOMContentLoaded", function() {
		Behaviour.apply();
	}, false);
}
/*@cc_on @*/
/*@if (@_win32)
	document.write("<script src=getElementsBySelector_ie.js><"+"/script>");
	document.write("<script defer src=ie_onload.js><"+"/script>");
/*@end @*/

if (document.evaluate) {
    document.write("<script src=getElementsBySelector_xpath.js><"+"/script>");
}
