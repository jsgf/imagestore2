dojo.require("dojo.crypto.MD5");
dojo.require("dojo.json");

var user = 'admin';
var pass = 'admin';
var auth_response = {};

function set_userpass(_user, _pass)
{
	if (_user == user && _pass == pass)
		return;

	user = _user;
	pass = _pass;
	auth_response = {};
}

// This matches name=value, where value can either be a number, an identifier or a quoted string.
var authitem = /\s*([a-z_][a-z0-9_-]*)\s*=\s*(\d+|[a-z_][a-z0-9_-]*|"([^"]*)"),?\s*(.*)$/i; // "

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
	method = method.toUpperCase();

	response = {
		username: user,
		realm: challenge.realm,
		nonce: challenge.nonce,
		uri: uri,

		nc: authcount++,
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
	
	for (k in response) {
		var r = dojo.lang.reprString(response[k].toString());
		//alert('k='+k+' -> '+r);
		ret.push(k + '=' + r);
	}

	ret = ret.join(',');
	
	//alert(['user=', user, 'pass=', pass, 'method=', method, 'uri=', uri, 'challenge=', challenge].join(' '));

	alert('ret='+ret);

	return 'Digest '+ret;
}

// Request a URL.  If we have been given a username and password, then
// prepare to answer an authentication response.  Also keeps a cache
// of responses for each uri, so that if we see it again, we can just
// supply the response without being asked.
function request(origreq, challenge)
{
	req = dojo.lang.shallowCopy(origreq);

	if (user && pass) {
		// If we have a challenge, then generate a response
		if (challenge) {
			var method = req.method;
			if (!method)
				method = 'get';
			var auth = authenticate(user, pass, method.toUpperCase(),
						req.url, parse_challenge(challenge));
			auth_response[req.url] = auth;
		}

		// If we have a response, then be prepared to use it
		if (auth_response[req.url]) {
			var auth = auth_response[req.url];

			//alert('url='+req.url+' auth='+auth);
			if (req['headers'] == null)
				req['headers'] = { };
			req['headers']['x-authorization'] = auth;
			req['headers']['authorization'] = auth;
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

		//alert('req.headers.keys='+req.headers);
	}

	req.sendTransport = false;

	dojo.io.bind(req);
}

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

authcount = 1;


//authenticate('admin', 'admin');

poke = {
	url: '/imagestore/default/1/',
	load: function(type, data, event) {
		alert('loaded OK');
	},
	error: function(type, data, event) {
		alert('error ' + event.status);
	}
};
request(poke);
