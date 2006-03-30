var widget = {};	// widget package

djConfig.isDebug=false;
djConfig.debugContainerId = 'log';

var log = dojo.debug;

dojo.require("dojo.crypto.MD5");
dojo.require("dojo.json");

dojo.require('widget.Login');

var base_path = '/imagestore/';

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
				this._publish('valid', { fullname: this.fullname, id: this.userid });
				break;
			case 'invalid':
				this._publish('invalid', this.user, '');
				break;
			default:
				alert('bad auth state:'+this.state);
			}
		}
	},

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

	logout: function() {
		this.user = null;
		this.pass = null;
		this.response = {};

		document.cookie = 'IS-authorization=;path='+base_path+';max-age=0;';

		this._setstate('unset');

		this.update_auth();
	},

	_publish: function() {
		dojo.debug('auth publish: '+arguments[0]);
		dojo.event.topic.publish('IS/Auth', arguments);		
	},

	_setstate: function(state, fullname, userid) {
		log('this.state '+this.state+' -> '+state+'('+fullname+','+userid+')');
		this.state = state;
		this.fullname = fullname;
		this.userid = userid;
	},

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
					_this._setstate('valid', data.fullname, data.id);
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

		log("validating auth token");
	
		request(req);
	},

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

	authorize_request: function(origreq) {
		var req = dojo.lang.shallowCopy(origreq);

		if (this.state != 'unset') {
			if (!this.response[req.url]) {
				challenge = this._get_challenge();
				//alert('got challenge for '+origreq.url+': '+challenge);
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

				//alert('url='+req.url+' auth='+auth);
				if (req['headers'] == null)
					req['headers'] = { };
				req['headers']['authorization'] = resp;
				// Opera, at least, seems to eat JS-created Authorization headers
				req['headers']['x-authorization'] = resp;
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


// Request a URL.  If we have been given a username and password, then
// prepare to answer an authentication response.  Also keeps a cache
// of responses for each uri, so that if we see it again, we can just
// supply the response without being asked.
function request(origreq, challenge)
{
	var req = window.auth.authorize_request(origreq);

	req.sendTransport = false;
	req.preventCache = true;

	dojo.io.bind(req);
}

// Subscribe the auth object to events coming from the auth UI
dojo.event.topic.subscribe('IS/Auth/UI', auth, 'authevent');
// Make sure the auth object has up-to-date information
dojo.addOnLoad(function () { window.auth.update_auth() });

poke = {
	url: base_path+'default/1/meta/id',
	mimetype: 'text/json',

	load: function(type, data, event) {
		alert('loaded OK: '+data);
	},
	error: function(type, data, event) {
		alert('error ' + event.status);
	}
};
//request(poke, true);
