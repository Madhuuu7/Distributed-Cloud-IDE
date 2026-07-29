import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import AuthCard from "../components/auth/AuthCard";
import { authApi } from "../services/api";

export default function SignupPage() {

    const navigate = useNavigate();

    const [fullName,setFullName] = useState("");
    const [email,setEmail] = useState("");
    const [password,setPassword] = useState("");

    async function handleSignup(){

        try{

            const res = await authApi.signup({
                full_name: fullName,
                email,
                password
            });

            localStorage.setItem(
                "token",
                res.data.access_token
            );

            navigate("/dashboard");

        }catch(err){

            alert("Signup failed");

        }

    }

    return (

        <AuthCard
            title="Create your account"
            subtitle="Start building"
        >

            <div className="space-y-4">

                <input
                    value={fullName}
                    onChange={(e)=>setFullName(e.target.value)}
                    placeholder="Full Name"
                    className="w-full rounded-lg border border-slate-700 bg-slate-950 p-3"
                />

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
                    onClick={handleSignup}
                    className="w-full rounded-lg bg-brand-500 p-3"
                >
                    Create Account
                </button>

                <Link to="/login">
                    Already have an account?
                </Link>

            </div>

        </AuthCard>

    );

}