dojo.require("dojo.crypto.MD5");
dojo.require("dojo.json");
dojo.require("dojo.io.cookie");

var base_path = '/imagestore/';

var authstate = {
	state: 'unset',		// unset, set, valid, invalid
	user: null,
	pass: null,
	response: {},
	challenge: null,
	challenge_expire: 0,
	authcount: 1
};

function setstate(state)
{
	log('authstate.state '+authstate.state+' -> '+state);
	authstate.state = state;
}

function set_userpass(user, pass)
{
	if (user == '')
		user = null;
	if (pass == '')
		pass = null;

	if (user == null || pass == null)
		return logout();

	if (user == authstate.user && pass == authstate.pass) {
		log("setpass unchanged: "+authstate.pass+", "+authstate.pass);
		return;
	}

	log("setpass changed: "+user+", "+pass);

	setstate('set');

	authstate.user = user;
	authstate.pass = pass;
	authstate.response = {};
	//authstate.challenge = null;

	window.user = user;
	window.pass = pass;

	update_auth();
}

function logout()
{
	setstate('unset');

	authstate.user = null;
	authstate.pass = null;

	document.cookie = 'IS-authorization=-;path='+base_path+';max-age=0;';

	update_auth();
}

function log(str)
{
	//return;

	l = dojo.byId("log");

	if (l)
		l.innerHTML += str + "<br>\n";
}

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
*/

// This matches name=value, where value can either be a number, an identifier or a quoted string.
var authitem = /\s*([a-z_][a-z0-9_-]*)\s*=\s*(\d+|[a-z_][a-z0-9_-]*|"([^"]*)"),?\s*(.*)$/i; // ";

function parse_challenge(authhdr)
{
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
		value = matches[2];
		if (matches[3] != null)
			value = matches[3];

		authhdr = matches[4];

		//alert('name='+name+' value='+value);
		
		ret[name] = value;
	}

	return ret;
}

// Given some details and a challenge, generate a digest authorization
// header string
function authenticate(user, pass, method, uri, challenge)
{
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

	response = {
		username: user,
		realm: challenge.realm,
		nonce: challenge.nonce,
		uri: uri,

		nc: authstate.authcount++,
		cnonce: Math.floor(Math.random() * 1000000000).toString(),
		qop: 'auth'
	};

	var pieces = [ response.nonce ];

	if (challenge.qop)
		pieces = pieces.concat(response.nc,
				       response.cnonce,
				       response.qop);

	pieces = pieces.concat(H(A2(method, response.uri)));

	response.response = KD(H(A1(user, response.realm, pass)),
			       pieces.join(':'));

	var ret = [];
	
	for (var k in response) {
		var r = dojo.lang.reprString(response[k].toString());
		//alert('k='+k+' -> '+r);
		ret.push(k + '=' + r);
	}

	ret = ret.join(',');
	
	//alert(['user=', user, 'pass=', pass, 'method=', method, 'uri=', uri, 'challenge=', challenge].join(' '));

	//alert('ret='+ret);

	return 'Digest '+ret;
}

function get_challenge()
{
	var now = Math.floor((new Date()).getTime() / 1000); // milliseconds to seconds

	if (authstate.challenge &&
	    (authstate.challenge_expire == 0 || authstate.challenge_expire > now))
		return authstate.challenge;

	if (0)
		alert('getting new challenge: now='+now+
		      ' authstate.challenge='+ authstate.challenge+
		      ' authstate.challenge_expire='+authstate.challenge_expire);
	

	var ret = null;

	var req = {
		url: base_path+'auth/challenge',
		mimetype: 'text/json',
		sync: true,
		sendTransport: false,
		preventCache: true,
		load: function(type, data, event) {
			ret = data;
			//alert('got challenge: '+data);
		},
		error: function(type, data, event) {
			alert('get challenge failed: '+event.error);
		}
	};
	dojo.io.bind(req);

	if (ret) {
		authstate.challenge_expire = ret.expire;
		if (authstate.challenge_expire)
			authstate.challenge_expire -= (60); // give 60 sec leeway
		authstate.challenge = ret.challenge;
	}

	return authstate.challenge;
}

// Request a URL.  If we have been given a username and password, then
// prepare to answer an authentication response.  Also keeps a cache
// of responses for each uri, so that if we see it again, we can just
// supply the response without being asked.
function request(origreq, challenge)
{
	var req = dojo.lang.shallowCopy(origreq);

	if (authstate.state != 'unset') {
		// If we have no response, pre-get a challenge so we
		// can avoid a 401 error
		if (!challenge && !authstate.response[req.url]) {
			challenge = get_challenge();
			//alert('got challenge for '+origreq.url+': '+challenge);
		}

		// If we have a challenge, then generate a response
		if (challenge) {
			var method = req.method;
			if (!method)
				method = 'get';
			var auth = authenticate(authstate.user, authstate.pass,
						method.toUpperCase(),
						req.url, parse_challenge(challenge));
			authstate.response[req.url] = auth;
		}

		// If we have a response, then be prepared to use it
		if (authstate.response[req.url]) {
			var auth = authstate.response[req.url];

			//alert('url='+req.url+' auth='+auth);
			if (req['headers'] == null)
				req['headers'] = { };
			req['headers']['authorization'] = auth;
			// Opera, at least, seems to eat JS-created Authorization headers
			req['headers']['x-authorization'] = auth;
		} else {
			// If we have no response, then be prepared to generate one.
			req.error = function (type, data, event) {
				if (event.status == 401) { // Unauthorized
					var challenge = event.getResponseHeader('www-authenticate');
					request(origreq, challenge);
				} else
					return origreq.error(type, data, event);
			}
		}
	}

	req.sendTransport = false;
	req.preventCache = true;

	dojo.io.bind(req);
}

function update_auth() {
	var progress = dojo.byId("login.progress");
	var login = dojo.byId('login');
	var loginuser = dojo.byId('login.user');
	var loginpass = dojo.byId('login.pass');
	loginuser.value = authstate.user;
	loginpass.value = authstate.pass;

	var req = {
		url: base_path+'auth/user',
		mimetype: 'text/json',

		error: function(type, data, event) {
			alert('user probe failed: '+event.status);
		},
		load: function(type, data, event) {
			var form = dojo.byId('login.form');
			var state = dojo.byId('login.state');
			var loginid = dojo.byId('login.loginid');

			log('update_auth: user='+data+' auth.state='+authstate.state);

			progress.style.display = 'none';

			if (data != null) {
				setstate('valid');
				
				log('data.username='+data.username+' fullname='+data.fullname);

				loginid.innerHTML = data.fullname;
				form.style.display = 'none';
				state.style.display = 'inline';
			} else {
				if (authstate.state == 'set')
					setstate('invalid');
				else
					setstate('unset');

				loginid.innerHTML = 'Not logged in';
				form.style.display = 'block';
				state.style.display = 'none';
			}
			login.className = 'auth-' + authstate.state;
		}
	};

	log("updating auth");
	
	login.className = 'auth-' + authstate.state;
	progress.setAttribute('style', 'display:inline');

	request(req);
}

dojo.addOnLoad(update_auth);

function setup_events()
{
	var login_submit = dojo.byId('login.submit');
	var login_user = dojo.byId('login.user');
	var login_pass = dojo.byId('login.pass');

	log('login_submit='+login_submit);

	function submit_login () {
		var user = login_user.value;
		var pass = login_pass.value;
		
		set_userpass(user, pass);
	}
	dojo.event.connect(login_submit, 'onclick', submit_login);
	dojo.event.connect(login_pass, 'onblur', submit_login);
}

dojo.addOnLoad(setup_events);

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
