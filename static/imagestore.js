
djConfig.isDebug=false;
djConfig.debugContainerId = 'log';

if (typeof(base_path) == 'undefined')
	alert('base_path not set');

var log = dojo.debug;

dojo.require("dojo.crypto.MD5");
dojo.require("dojo.json");
dojo.require("dojo.io.cookie");

var widget = {};	// widget package
dojo.require('widget.Login');

/*
  Authentication algorithm:
  - if we have a cached token for URL, then use it immediately,

  otherwise
  - get a challenge from auth/challenge
  - generate response
  - cache reponse for URL

  This should mean that we always avoid getting an explicit error 401
  from the server, which will avoid the browser's dialog.

  The challenge is common to all responses (it is not URI-specific),
  so it is cached to save on turnarounds.

  Also, the server's authenticator sets a cookie, which is used in the
  case where this code has no useful authentication information.
*/


var auth = {
	state: 'unset',		// unset, set, valid, invalid
	user: null,
	pass: null,
	response: {},
	challenge: null,
	challenge_expire: 0,
	authcount: 1,

	userid: null,		// set when state valid
	fullname: null,		// set when state valid

	// Called on page load to set auth state
	set_auth: function(userid, username, fullname) {
		var user = { id: userid,
			     username: username,
			     fullname: fullname };
		this._setstate('valid', user);
		this._publish('valid', user);
	},

	// Called by login UI widget to make auth state changes
	authevent: function(event, user, pass) {
		log('auth.authevent: '+event+' user="'+user+'" pass="'+pass+'"');

		switch(event) {
		case 'login':
			this.login(user, pass);
			break;

		case 'logout':
			this.logout();
			break;

		case 'update':
			switch(this.state) {
			case 'unset':
				this._publish('unauth');
				break;
			case 'set':
				this._publish('details', this.user, this.pass);
				break;
			case 'valid':
				var this_ = this;
				this._publish('valid', { id: this_.userid,
							 username: this_.user,
							 fullname: this_.fullname });
				break;
			case 'invalid':
				this._publish('invalid', this.user, '');
				break;
			default:
				alert('bad auth state:'+this.state);
			}
		}
	},

	// user wants to log in
	login: function(user, pass) {
		if (user == '')
			user = null;
		if (pass == '')
			pass = null;

		if (user == null || pass == null)
			this.logout();

		if (user == this.user && pass == this.pass) {
			log("setpass unchanged: "+this.pass+", "+this.pass);
			return;
		}

		log("setpass changed: "+user+", "+pass);

		this.user = user;
		this.pass = pass;
		this.response = {};

		this._setstate('set');

		this.update_auth();
	},

	// user wants to log out
	logout: function() {
		this.user = null;
		this.pass = null;
		this.response = {};

		document.cookie = 'IS-authorization=;path='+base_path+';max-age=0;';

		this._setstate('unset');

		this.update_auth();
	},

	// tell anyone who cares about something
	_publish: function() {
		dojo.debug('auth publish: '+arguments[0]);
		if (typeof(arguments[1]) != 'undefined') {
			var u = arguments[1];
			dojo.debug('id='+u.id+' user '+u.username+' full '+u.fullname);
		}
		dojo.event.topic.publish('IS/Auth', arguments);		
	},

	// set current auth state
	_setstate: function(state, user) {
		log('this.state '+this.state+' -> '+state);
		this.state = state;
		if (user) {
			log(' user.fullname='+user.fullname+' username='+user.username+' id='+user.id);
			this.userid = user.id;
			this.user = user.username;
			this.fullname = user.fullname;
		}
	},

	// check with the server to see what our auth state really is
	update_auth: function() {
		var _this = this;

		var req = {
			url: base_path+'auth/user',
			mimetype: 'text/json',

			error: function(type, data, event) {
				alert('user probe failed: '+event.status);
			},
			load: function(type, data, event) {
				log('update_auth: user="'+data+'" this.state='+_this.state);

				if (data) {
					_this._setstate('valid', data);
					_this._publish('valid', data);
				} else {
					if (_this.state == 'set') {
						_this._setstate('invalid');
						_this._publish('invalid');
					} else {
						_this._setstate('unset');
						_this._publish('unauth');
					}
				}
			}
		};

		log("validating auth token user "+this.user);
	
		request(req);
	},

	// compute a response for HTTP Digest authentication
	_auth_response: function(method, uri, challenge) {
		function H(x) {
			return dojo.crypto.MD5.compute(x, dojo.crypto.outputTypes.Hex);
		}

		function KD(secret, data) {
			return H([ secret, data ].join(':'));
		}

		function A1(user, realm, password) {
			return [ user, realm, password ].join(':');
		}

		function A2(method, uri) {
			return [ method, uri ].join(':');
		}

		method = method.toUpperCase();

		var _this = this;

		var response = {
			username: _this.user,
			realm: challenge.realm,
			nonce: challenge.nonce,
			uri: uri,

			nc: _this.authcount++,
			cnonce: Math.floor(Math.random() * 1000000000).toString(),
			qop: 'auth'
		};

		var pieces = [ response.nonce ];

		if (challenge.qop)
			pieces = pieces.concat(response.nc,
					       response.cnonce,
					       response.qop);

		pieces = pieces.concat(H(A2(method, response.uri)));

		response.response = KD(H(A1(this.user, response.realm, this.pass)),
				       pieces.join(':'));

		var ret = [];
	
		for (var k in response) {
			var r = dojo.lang.repr(response[k].toString());
			//alert('k='+k+' -> '+r);
			ret.push(k + '=' + r);
		}

		ret = ret.join(',');
	
		return 'Digest '+ret;
	},

	// parse an HTTP Digest authentication challenge
	_parse_challenge: function(authhdr) {
		// This matches name=value, where value can either be
		// a number, an identifier or a quoted string.
		var authitem = /\s*([a-z_][a-z0-9_-]*)\s*=\s*([0-9a-f]+|[a-z_][a-z0-9_-]*|"((?:[^"\\]|\\[^0-7]|\\[0-7]{1,3})*)")(?:\s*,)?\s*(.*)$/i; // ))";

		if (authhdr.split(/\W+/)[0] != 'Digest')
			alert('bad scheme: '+authhdr);
		else
			authhdr = authhdr.replace(/^Digest\s+/, '');

		ret = {};

		//alert('authhdr="'+authhdr+'" len='+authhdr.length);

		while (authhdr.length > 0) {
			var matches = authitem.exec(authhdr);

			if (matches == null)
				break;
		
			//alert('authitem='+authitem+' matches='+matches);

			var name, value;

			name = matches[1];
			value = unescape(matches[3] || matches[2]);	// [3] is the unquoted string

			authhdr = matches[4];	// remaining string

			//log('name='+name+' value='+value);
		
			ret[name] = value;
		}
		
		return ret;
	},

	_get_challenge: function() {
		var now = Math.floor((new Date()).getTime() / 1000); // milliseconds to seconds

		if (this.challenge &&
		    (this.challenge_expire == 0 || this.challenge_expire > now))
			return this.challenge;

		if (0)
			alert('getting new challenge: now='+now+
			      ' this.challenge='+ this.challenge+
			      ' this.challenge_expire='+this.challenge_expire);
	

		var ret = null;

		var req = {
			url: base_path+'auth/challenge',
			mimetype: 'text/json',
			sync: true,
			sendTransport: false,
			preventCache: true,
			load: function(type, data, event) {
				ret = data;
				//log('challenge: '+data);
			},
			error: function(type, data, event) {
				alert('get challenge failed: '+event.error);
			}
		};
		dojo.io.bind(req);

		if (ret) {
			this.challenge_expire = ret.expire;
			if (this.challenge_expire)
				this.challenge_expire -= (60); // give 60 sec leeway
			this.challenge = ret.challenge;
		}

		return this.challenge;
	},

	// Make sure a request has authorizing information attached to it, if we have it
	authorize_request: function(origreq) {
		var req = dojo.lang.shallowCopy(origreq);

		if (this.state != 'unset' && this.pass != null) {
			if (!this.response[req.url]) {
				challenge = this._get_challenge();
				log('got challenge for '+origreq.url+': '+challenge);
			}

			// If we have a challenge, then generate a response
			if (challenge) {
				var method = req.method;
				if (!method)
					method = 'get';
				this.response[req.url] =
					this._auth_response(method.toUpperCase(), req.url,
							    this._parse_challenge(challenge));
			}

			// If we have a response, then be prepared to use it
			if (this.response[req.url]) {
				var resp = this.response[req.url];

				log('url='+req.url+' auth='+resp);
				//_set_req_header(req, 'authorization', resp);
				_set_req_header(req, 'x-authorization', resp);
			} else {
				// If we have no response, then be prepared to generate one.
				req.error = function (type, data, event) {
					if (event.status == 401) { // Unauthorized
						this.challenge = event.getResponseHeader('www-authenticate');
						dojo.io.bind(this.authorize_request(origreq));
					} else
						return origreq.error(type, data, event);
				}
			}
		}

		return req;
	}
};

function _set_req_header(req, header, value)
{
	if (!('headers' in req))
		req['headers'] = {}
	req['headers'][header] = value;
}

// Request a URL.  If we have been given a username and password, then
// prepare to answer an authentication response.  Also keeps a cache
// of responses for each uri, so that if we see it again, we can just
// supply the response without being asked.
function request(origreq, challenge)
{
	var req = window.auth.authorize_request(origreq);
	var types = [ 'text/plain', 'text/html', 'text/json',
		      'application/json', 'text/xml',
		      'application/xml', 'application/xhtml+xml' ];

	req.sendTransport = false;
	req.preventCache = true;

	// Set what types we want to see based on the request's
	// mimetype property.
	var accept = [];
	if (req.mimetype) {
		for(var i = 0; i < types.length; i++) {
			if (types[i] != req.mimetype)
				accept.push(types[i] + ';q=0.9');
			else
				accept.push(types[i]);
		}
	} else
		for(var i = 0; i < types.length; i++)
			accept.push(types[i]);
	accept.push('text/*;q=0.5');

	_set_req_header(req, 'Accept', accept.join(','));

	dojo.io.bind(req);
}

// Update the auth classes on BODY so the auth-sensitive styles work.
// Responds to events published by the auth object.
auth_styles = {
	update: function(event) {
		var from, to;

		if (event == 'valid') {
			from = 'no-auth';
			to = 'auth';
		} else {
			from = 'auth';
			to = 'no-auth';
		}
		dojo.html.replaceClass(dojo.html.body(), to, from);
	}
};
dojo.event.topic.subscribe('IS/Auth', auth_styles, 'update');

// Subscribe the auth object to events coming from the auth UI
dojo.event.topic.subscribe('IS/Auth/UI', auth, 'authevent');

// Make sure the auth object has up-to-date information
// XXX Should only be necessary if the server didn't already prime us with auth info
dojo.addOnLoad(function () { window.auth.update_auth() });



/*
  Try to resize the window to a useful inner size.
  - do the simple thing
  - see if it worked
  - if not, try again

  XXX FIXME: apparently IE doesn't support innerWidth/Height,
  and you have to use something else.  See
  http://webfx.eae.net/dhtml/wincontrols/wincontrols.html
*/
function size_window(win, w,h)
{
	var bw = w - win.innerWidth;
	var bh = h - win.innerHeight;

	//alert('w='+w+' h='+h+' bw='+bw+' bh='+bh);

	if (bw != 0 || bh != 0)
		win.resizeTo(w + bw, h + bh);
}

function create_sized_window(url,id,w,h,extra)
{
	if (!extra)
		extra = [];

	extra.push('width='+w);
	extra.push('height='+h);
	extra = extra.join(',');

	//alert(extra);

	var win = window.open(url, id, extra);

	size_window(win, w, h);

	win.focus();		// pop up existing window

	return win;
}

function create_view_window(id, pw, ph, portrait, padding, extra)
{
	var size = get_preference('image_size', [ '', [ 640, 480 ] ]);
	
	var sw = size[1][0];
	var sh = size[1][1];

	if (portrait) {
		var t = pw;
		pw = ph;
		ph = t;
	}

	var w, h;

	if (pw < sw && ph < sh) {
		w = pw;
		h = ph;
	} else {
		var fx = sw / pw;
		var fy = sh / ph;

		if (fx < fy) {
			w = sw;
			h = ph * fx;
		} else {
			w = pw * fy;
			h = sh;
		}
	}

	return create_sized_window('', id, w+padding, h+padding, extra);
}



function set_want_edit(on)
{
	var set, clear;

	if (on) {
		set = 'want-edit';
		clear = 'no-want-edit';
	} else {
		set = 'no-want-edit';
		clear = 'want-edit';
	}
	set_preference('want_edit', on);
	dojo.html.replaceClass(dojo.html.body(), set, clear);
}



function set_preference(pref, val)
{
	val = dojo.json.serialize(val);
	document.cookie = 'IS-pref-'+pref+'='+val+';path='+base_path;
}

function get_preference(pref, defl)
{
	pref = 'IS-pref-'+pref;
	var val = dojo.io.cookie.getCookie(pref);
	if (val != null)
		val = dojo.json.evalJSON(val);
	else
		val = defl;
	return val;
}


function find_alert(container)
{
	var divs = container.getElementsByTagName('div');
	for(var i = 0; i < divs.length; i++) {
		var div = divs[i];
		if (dojo.html.hasClass(div, 'alert')) {
			return div;
		}
	}
	return null;
}

function set_error(container, message)
{
	var alert = find_alert(container);

	if (alert != null) {
		alert.style.display = 'block';
		alert.title = message;
	}
}

function clear_error(container)
{
	var alert = find_alert(container);

	if (alert != null) {
		alert.style.display = 'none';
		alert.title = '';
	}
}

// Handle thumbnail rotation.  This assumes 'container' refers to the
// outer DIV of a thumbnail on a page.  It sends the request to the
// server to actually rotate the image, and the server returns the new
// thumbnail size and position, which is used to update the page.
//
// XXX Is there a better way to handle IMG reloads without just
// tacking '?'s onto the end of the SRC URL?
function do_rotate(container, action, angle, post)
{
	req = {
		url: action,
		mimetype: 'text/json',
		method: 'POST',
		content: { angle: angle },

		error: function(type, data, event) {
			//alert('rotate failed: '+event.status);
			set_error(container, 'Rotate failed: '+event.status);
			if (event.status == 401)
				window.auth.update_auth();
		},
		load: function(type, data, event) {
			var rot = data;
			var thumb = rot.thumb;

			clear_error(container);

			if (0)
				alert('thumb='+thumb +
				      ' thumb.width='+thumb.width +
				      ' thumb.height='+thumb.height +
				      ' thumb.pos_left='+thumb.pos_left +
				      ' thumb.pos_top='+thumb.pos_top);

			// Update the IMGs width, height and position styles
			var img = container.getElementsByTagName('img');
			if (img.length != 1) {
				alert('no IMG in container');
				return;
			}
			img = img[0];

			//alert('IMG.src='+img.src+' style='+img.style);

			img.style.width = thumb.width + 'px';
			img.style.height = thumb.height + 'px';
			img.style.left = thumb.pos_left + 'px';
			img.style.top = thumb.pos_top + 'px';

			// Force image reload somehow...
			var src = img.src;
			if (src.indexOf('?') != -1)
				src = img.src.split(/\?/)[0];
			img.src = src + '?' + rot.image.orientation;

			// update the FORM INPUT values to reflect the new orientation
			var inputs = container.getElementsByTagName('input');
			
			for(var i = 0; i < inputs.length; i++) {
				var input = inputs[i];

				if (input.name != 'angle')
					continue;

				if (dojo.html.hasClass(input, 'right'))
					input.value = rot.rot90.toString();
				else if (dojo.html.hasClass(input, 'down'))
					input.value = rot.rot180.toString();
				else if (dojo.html.hasClass(input, 'left'))
					input.value = rot.rot270.toString();
			}

		}
	};

	request(req);
}


// Behaviours

var wantedit_rules = {
        'A.set-wantedit': function(el) {
                el.onclick = function () { set_want_edit(true); return false; }
                el = null;      // break cycle
	},
        'A.set-nowantedit': function(el) {
                el.onclick = function () { set_want_edit(false); return false; }
                el = null;      // break cycle
	},
};
Behaviour.register(wantedit_rules);

var hover_rules = {
        '.hoverable': function(el) {
                el.onmouseover = function() { dojo.html.addClass(this, 'hover'); }
                el.onmouseout  = function() { dojo.html.removeClass(this, 'hover'); }
                el = null;      // break cycle
	},
};
Behaviour.register(hover_rules);

var img_form_rules = {
        '.thumbnail FORM INPUT.arrow': function(el) {
                el.onclick = function() {
                        var form = this.parentNode;
                        form.angle = this.value;
                }
        },
        '.thumbnail FORM.rotate': function(el) {
                el.onsubmit = function() {
                        var container = this.parentNode.parentNode;
                        do_rotate(container, this.action, this.angle,
                                  function () {
					  alert('applying behaviour: '+container.innerHTML);
					  Behaviour.apply()
						  });
                        return false;
                }
                el = null;      // break cycle
        },
	'.alert': function(el) {
		el.onclick = function() {
			clear_error(this.parentNode);
		}
		el = null;
	}
};
Behaviour.register(img_form_rules);
