import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import AuthCard from "../components/auth/AuthCard";
import { authApi } from "../services/api";

export default function LoginPage() {

    const navigate = useNavigate();

    const [email,setEmail] = useState("");
    const [password,setPassword] = useState("");

    async function handleLogin(){

        try{

            const res = await authApi.login({
                email,
                password
            });

            localStorage.setItem(
                "token",
                res.data.access_token
            );

            navigate("/dashboard");

        }catch(err){

            alert("Invalid credentials");

        }

    }

    return (

        <AuthCard
            title="Welcome Back"
            subtitle="Sign in"
        >

            <div className="space-y-4">

                <input
                    value={email}
                    onChange={(e)=>setEmail(e.target.value)}
                    placeholder="Email"
                    className="w-full rounded-lg border border-slate-700 bg-slate-950 p-3"
                />

                <input
                    type="password"
                    value={password}
                    onChange={(e)=>setPassword(e.target.value)}
                    placeholder="Password"
                    className="w-full rounded-lg border border-slate-700 bg-slate-950 p-3"
                />

                <button
                    onClick={handleLogin}
                    className="w-full rounded-lg bg-brand-500 p-3"
                >
                    Login
                </button>

                <Link to="/signup">
                    Create account
                </Link>

            </div>

        </AuthCard>

    );

}