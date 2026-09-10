"""Encrypt a published page so only someone with the key can read it.

GitHub Pages is a static host: there is no server to check a password against.
A page that merely *asks* for one and then reveals content it already contains
protects nothing — the board would sit in the HTML for anyone who pressed
Ctrl-U or ran `curl`.

So the page is genuinely encrypted. What GitHub serves is a short unlock form
plus a block of AES-256-GCM ciphertext. The key is derived in the reader's
browser with PBKDF2-SHA256 and never travels anywhere; a wrong key fails the
GCM authentication tag and decrypts to nothing at all. `curl` on the URL
returns ciphertext.

What this is not: protection against someone who has the key, and not
protection against an attacker willing to grind guesses offline against the
downloaded file. That is why the key generated for this is 80 bits of
randomness rather than a word anyone could guess.
"""

from __future__ import annotations

import base64
import json
import os
import secrets

PBKDF2_ITERATIONS = 250_000
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no I, L, O, 0, 1


def new_key(groups: int = 4, size: int = 4) -> str:
    """A key strong enough to survive offline guessing, still readable aloud."""
    return "-".join(
        "".join(secrets.choice(_ALPHABET) for _ in range(size)) for _ in range(groups)
    )


def encrypt(plaintext: str, key: str) -> dict:
    """AES-256-GCM under a PBKDF2 key. Returns the parts the browser needs."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt = os.urandom(16)
    iv = os.urandom(12)
    import hashlib

    derived = hashlib.pbkdf2_hmac("sha256", key.encode("utf-8"), salt,
                                  PBKDF2_ITERATIONS, dklen=32)
    blob = AESGCM(derived).encrypt(iv, plaintext.encode("utf-8"), None)
    b64 = lambda b: base64.b64encode(b).decode("ascii")  # noqa: E731
    return {"salt": b64(salt), "iv": b64(iv), "ct": b64(blob),
            "iterations": PBKDF2_ITERATIONS}


GATE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>__TITLE__</title>
<style>
  :root{ --bg:#0e0b16; --panel:#191330; --line:#2f2547; --text:#ece9f5;
         --muted:#a79dc8; --accent:#ff4d9b; --bad:#ff6b81; }
  *{box-sizing:border-box; border-radius:0 !important}
  body{margin:0; min-height:100vh; background:var(--bg); color:var(--text);
    display:flex; align-items:center; justify-content:center; padding:24px;
    font-family:"JetBrainsMono Nerd Font",ui-monospace,"JetBrains Mono",Menlo,Consolas,monospace;
    font-size:13.5px; line-height:1.6}
  .box{border:1px solid var(--line); background:var(--panel); max-width:420px; width:100%}
  .head{background:var(--accent); color:#12030c; font-weight:700; letter-spacing:.09em;
    padding:6px 14px; font-size:12.5px}
  .body{padding:18px 16px}
  p{margin:0 0 14px; color:var(--muted); font-size:12.5px}
  form{display:flex; gap:0; border:1px solid var(--line)}
  input{flex:1; min-width:0; background:transparent; border:none; outline:none;
    color:var(--text); font:inherit; padding:8px 11px; letter-spacing:.12em}
  input::placeholder{color:var(--muted); letter-spacing:.06em}
  button{background:var(--accent); color:#12030c; border:none; font:inherit;
    font-weight:700; padding:8px 16px; cursor:pointer}
  button:disabled{opacity:.6; cursor:default}
  .msg{margin-top:12px; font-size:12.5px; min-height:1.4em; color:var(--muted)}
  .msg.bad{color:var(--bad)}
</style></head><body>
<div class="box">
  <div class="head">__TITLE__</div>
  <div class="body">
    <p>This board is private. Enter the key you were given.</p>
    <form id="f" autocomplete="off">
      <input id="k" type="password" placeholder="XXXX-XXXX-XXXX-XXXX"
             autocapitalize="characters" spellcheck="false" autofocus>
      <button id="go" type="submit">open</button>
    </form>
    <div class="msg" id="m"></div>
  </div>
</div>
<script>
const P=__PAYLOAD__, STORE='radarkey:'+location.pathname;
const m=document.getElementById('m'), inp=document.getElementById('k'), go=document.getElementById('go');
const b=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));

async function unlock(key, quiet){
  if(!key) return false;
  go.disabled=true; m.className='msg'; m.textContent='unlocking…';
  try{
    const base=await crypto.subtle.importKey('raw',new TextEncoder().encode(key),'PBKDF2',false,['deriveKey']);
    const aes=await crypto.subtle.deriveKey(
      {name:'PBKDF2',salt:b(P.salt),iterations:P.iterations,hash:'SHA-256'},
      base,{name:'AES-GCM',length:256},false,['decrypt']);
    const plain=await crypto.subtle.decrypt({name:'AES-GCM',iv:b(P.iv)},aes,b(P.ct));
    try{ sessionStorage.setItem(STORE,key); }catch(e){}
    const html=new TextDecoder().decode(plain);
    document.open(); document.write(html); document.close();
    return true;
  }catch(e){
    go.disabled=false;
    if(!quiet){ m.className='msg bad'; m.textContent='That key does not open this board.'; }
    else m.textContent='';
    try{ sessionStorage.removeItem(STORE); }catch(e2){}
    inp.select();
    return false;
  }
}

document.getElementById('f').onsubmit=e=>{ e.preventDefault(); unlock(inp.value.trim().toUpperCase(), false); };

// A key remembered for this tab, or one passed in the link's #fragment —
// fragments are never sent to the server, so a link can carry the key.
(async function(){
  const frag=new URLSearchParams(location.hash.slice(1)).get('k');
  if(frag){ history.replaceState(null,'',location.pathname+location.search);
            if(await unlock(frag.trim().toUpperCase(), true)) return; }
  let saved=null; try{ saved=sessionStorage.getItem(STORE); }catch(e){}
  if(saved) await unlock(saved, true);
})();
</script></body></html>
"""


def gate_page(plaintext_html: str, key: str, title: str) -> str:
    """The full unlock page: a form, and the board as ciphertext."""
    payload = encrypt(plaintext_html, key)
    return (GATE
            .replace("__PAYLOAD__", json.dumps(payload))
            .replace("__TITLE__", title))
