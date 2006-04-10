// written by Dean Edwards, 2006
// http://dean.edwards.name/weblog/2006/03/faster

// override Behaviour's register function
Behaviour._register = Behaviour.register
Behaviour.register = function(sheet) {
	Selectors.register(sheet);
	// call the old register function
	this._register(sheet);
}
// this object will manage CSS expressions used to query the DOM
var Selectors = {
	styleSheet: document.createStyleSheet(),
	cache: {},
	length: 0,
	
	register: function(sheet) {
		// create the CSS expression and add it to the style sheet
		var cssText = [], index;
		for (var selector in sheet) {
			index = this.length++;
			// have to store by index too as the expression hack does not like
			//  spaces in strings for some strange reason
			this.cache[index] = this.cache[selector] = [];
			cssText.push(selector + "{behavior:expression(Selectors.store(" + index + ",this))}");
		}
		this.styleSheet.cssText = cssText.join("\n");
	},
	
	store: function(index, element) {
		// called from the CSS expression
		// store the matched DOM node
		this.cache[index].push(element);
		element.runtimeStyle.behavior = "none";
	},
	
	tidy: function() {
		// clean up after behaviors have been applied
		delete this.cache;
		this.styleSheet.cssText = "";
	}
}
// override getElementsBySelector
document._getElementsBySelector = document.getElementsBySelector;
document.getElementsBySelector = function(selector) {
	if (!Selectors.cache || /\[/.test(selector)) { // attribute selectors not supported by IE5/6
		return document._getElementsBySelector(selector);
	} else { // use the cache
		return Selectors.cache[selector];
	}
};
