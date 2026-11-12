"use client";
import { useEffect, useState } from "react";
import { UserManager, WebStorageStateStore } from "oidc-client-ts";
export default function Callback() {
 const [status,setStatus] = useState("Completing sign-in…");
 useEffect(() => { const authority=process.env.NEXT_PUBLIC_OIDC_AUTHORITY||""; const client_id=process.env.NEXT_PUBLIC_OIDC_CLIENT_ID||""; const manager=new UserManager({authority,client_id,redirect_uri:window.location.origin+"/callback",response_type:"code",scope:"openid profile",userStore:new WebStorageStateStore({store:window.sessionStorage})}); manager.signinRedirectCallback().then(()=>window.location.replace("/")).catch(()=>setStatus("Sign-in failed. Please try again.")); },[]);
 return <main className="auth"><h1>AEP-X Hybrid IDE</h1><p>{status}</p><a href="/">Return to workspace</a></main>;
}
