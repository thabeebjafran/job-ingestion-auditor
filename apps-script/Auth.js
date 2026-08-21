/** Creates a short-lived OAuth 2.0 token using a service-account JSON key. */
function getServiceAccountAccessToken(serviceAccount) {
  if (!serviceAccount || !serviceAccount.client_email || !serviceAccount.private_key) {
    throw new Error('SERVICE_ACCOUNT_KEY must contain client_email and private_key.');
  }

  const now = Math.floor(Date.now() / 1000);
  const encode = value => Utilities.base64EncodeWebSafe(typeof value === 'string' ? value : JSON.stringify(value)).replace(/=+$/, '');

  const header = {
    alg: 'RS256',
    typ: 'JWT'
  };

  const claimSet = {
    iss: serviceAccount.client_email,
    scope: 'https://www.googleapis.com/auth/cloud-platform https://www.googleapis.com/auth/chat.bot',
    aud: 'https://oauth2.googleapis.com/token',
    iat: now,
    exp: now + 3600
  };

  const unsignedJwt = encode(header) + '.' + encode(claimSet);
  const signature = Utilities.computeRsaSha256Signature(unsignedJwt, serviceAccount.private_key);
  const assertion = unsignedJwt + '.' + Utilities.base64EncodeWebSafe(signature).replace(/=+$/, '');

  const response = UrlFetchApp.fetch('https://oauth2.googleapis.com/token', {
    method: 'post',
    contentType: 'application/x-www-form-urlencoded',
    payload: {
      grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
      assertion: assertion
    },
    muteHttpExceptions: true
  });

  const responseCode = response.getResponseCode();
  const responseBody = response.getContentText();

  if (responseCode !== 200) {
    throw new Error('OAuth token request failed (' + responseCode + '): ' + responseBody);
  }

  let tokenData;
  try {
    tokenData = JSON.parse(responseBody);
  } catch (_) {
    throw new Error('OAuth token response is not valid JSON: ' + responseBody);
  }

  if (!tokenData || !tokenData.access_token) {
    throw new Error('OAuth token response did not include access_token.');
  }

  return tokenData.access_token;
}

/** Standalone test function to verify OAuth 2.0 token generation using service account credentials. */
function testServiceAccountAuth() {
  const serviceAccount = JSON.parse(requireScriptProperty_('SERVICE_ACCOUNT_KEY'));
  console.log('Generating access token for:', serviceAccount.client_email);
  const token = getServiceAccountAccessToken(serviceAccount);
  console.log('Access token successfully retrieved! Prefix:', token.substring(0, 15) + '...');
  return token;
}
