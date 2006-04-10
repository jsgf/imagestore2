// written by Dean Edwards, 2006
// http://dean.edwards.name/weblog/2006/03/faster

document.recalc(true); // force evaluation of expressions
Behaviour.apply(); // apply behaviors
Selectors.tidy(); // clear down the selectors cache
