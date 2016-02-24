var React = require('react');
var ReactDOM = require('react-dom');

// ReactDOM.render(
//   <h1>Hi, world!</h1>,
//   document.getElementById('main')
// );

window.document.body.onclick = (e) => {
	let s = window.getSelection();
	console.log(s);
	console.log(s.getRangeAt(0).toString());
	let a = document.createElement('h1');
	a.textContent = 'click';
	window.document.body.appendChild(a);
}