dojo.provide('widget.Login');
dojo.provide('dojo.widget.Login');
dojo.provide('dojo.widget.html.Login');

dojo.require('dojo.widget.*');
dojo.require('dojo.event.topic');

dojo.widget.html.Login = function() {
	//dojo.debug('Login widget created');
	dojo.widget.HtmlWidget.call(this);

	this.templatePath = dojo.uri.dojoUri('widget/HtmlLogin.html');
	this.templateCssPath = dojo.uri.dojoUri('widget/HtmlLogin.css');

	this.widgetType = 'Login';

	// DOM nodes
	this.loginFormContainer = null;	// container for all

	// visible when not logged in
	this.notLoggedIn = null;

	// visible when validating a login
	this.validating = null;
	this.validatingUser = null;
	this.progress = null;

	// visible as we're entering details/invalid login
	this.loginForm = null;
	this.user = null;
	this.pass = null;
	this.login = null;
	this.cancel = null;
	this.loginFailed = null; // only in invalid

	// visible when we're validly logged in
	this.logoutForm = null;
	this.currentUser = null;

	// states are: notloggedin, entering, validating, valid, invalid
	this.state = '';

	this._publish = function() {
		dojo.event.topic.publish('IS/Auth/UI', arguments);
	}

	this.initialize = function() {
		this._setstate('notloggedin'); // initial guess for our state

		dojo.event.topic.subscribe('IS/Auth', this, this.auth_event);

		this._publish('update'); // get the auth subsystem to tell us its state
	}

	this.uninitialize = function() {
		dojo.event.topic.unsubscribe('IS/Auth', this, this.auth_event);
	}

	this.auth_event = function(event, user) {
		dojo.debug('Login auth_event: '+event);

		switch(event) {
		case 'invalid':
			this._setstate('invalid');
			break;
		case 'valid':
			dojo.debug('user: '+user+'; '+user.username);
			this._setstate('valid', user);
			break;
		case 'unauth':
			this._setstate('notloggedin');
			this.pass.value = '';
			break;
		}
	}

	this._setvisible = function(visset) {
		var flaggable = [ 'notLoggedIn', 'validating', 'loginForm', 'logoutForm', 'loginFailed' ];

		for(var i = 0; i < flaggable.length; i++) {
			var flag = flaggable[i];
			var set = false;

			for (var v = 0; v < visset.length; v++) {
				//dojo.debug('visset='+visset+'; flag='+flag+' v='+visset[v]);
				if (flag == visset[v]) {
					set = true;
					break;
				}
			}
			this[flag].style.display = set ? 'block' : 'none';
		}
	}

	this._setstate = function(state, user) {
		//dojo.debug('setting state '+this.state+' -> '+state);

		switch(state) {
		case 'notloggedin':
			this._setvisible([ 'notLoggedIn' ]);
			break;
		case 'invalid':
			this._setvisible([ 'loginForm', 'loginFailed' ]);
			this.user.focus();
			break;
		case 'entering':
			this._setvisible([ 'loginForm' ]);
			this.user.focus();
			break;
		case 'validating':
			this._publish('login', this.user.value, this.pass.value);
			this.validatingUser.innerHTML = this.user.value;
			this._setvisible([ 'validating' ]);
			break;
		case 'valid':
			this.user.value = user.username;
			this.currentUser.innerHTML = user.fullname;
		        // XXX need better way of getting base path
			this.currentUser.href = window.base_path+'user/'+user.username+'/';
			this._setvisible([ 'logoutForm' ]);
			break;
		default:
			alert('bad state '+state);
			return;
		}

		this.state = state;
	}
			    
	this.startEntry = function() {
		this._setstate('entering');
	}

	this.cancelLogin = function() {
		this._publish('logout');
	}

	this.submitLogin = function() {
		if (this.user.value == '' || this.pass.value == '') {
			//dojo.debug('this.user.value='+this.user.value+' pass='+this.pass.value);
			this.cancelLogin();
			return;
		}

		this._setstate('validating');
	}

	this.logout = function() {
		//dojo.debug('logging out');
		this.pass.value = '';
		this._publish('logout');
	}
};
dojo.inherits(dojo.widget.html.Login, dojo.widget.HtmlWidget);
dojo.widget.tags.addParseTreeHandler('dojo:login');
