import React, { useState } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { Lock, Mail, Eye, EyeOff, ShieldCheck, ArrowRight } from 'lucide-react';
import { useAuth } from '../hooks/useAuth';
import { useToast } from '../hooks/useToast';
import { Button } from '../components/common/Button';
import { Input } from '../components/common/Input';
import { ApiError } from '../types/api';

export const LoginPage: React.FC = () => {
  const { login } = useAuth();
  const { success } = useToast();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<{ message: string; requestId?: string | null } | null>(null);

  const from = location.state?.from?.pathname || '/dashboard';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!email.trim()) {
      setError({ message: 'Please enter your corporate email address.' });
      return;
    }

    if (!password) {
      setError({ message: 'Please enter your password.' });
      return;
    }

    setIsLoading(true);
    try {
      const user = await login({ email: email.trim(), password });
      success('Authentication Successful', `Welcome back, ${user.email}`);
      navigate(from, { replace: true });
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      setError({
        message: apiErr.message || 'Invalid email or password.',
        requestId: apiErr.requestId,
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 p-8 rounded-2xl shadow-2xl">
      <div className="text-left mb-8">
        <h2 className="text-2xl font-bold text-white tracking-tight">Enterprise Sign In</h2>
        <p className="text-xs text-slate-400 mt-1.5">
          Authenticate to access document intelligence, hybrid search, and RAG services.
        </p>
      </div>

      {error && (
        <div className="mb-6 p-4 rounded-xl bg-rose-950/70 border border-rose-800 text-rose-200 text-xs text-left">
          <p className="font-semibold">{error.message}</p>
          {error.requestId && (
            <p className="mt-1.5 font-mono text-[11px] text-rose-300">
              Request Correlation ID: {error.requestId}
            </p>
          )}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-5">
        <Input
          label="Corporate Email"
          type="email"
          autoComplete="email"
          placeholder="user@enterprise.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          leftIcon={<Mail className="w-4 h-4" />}
          disabled={isLoading}
          required
        />

        <div className="relative">
          <Input
            label="Password"
            type={showPassword ? 'text' : 'password'}
            autoComplete="current-password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            leftIcon={<Lock className="w-4 h-4" />}
            rightIcon={
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="text-slate-400 hover:text-slate-200 transition-colors"
                tabIndex={-1}
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            }
            disabled={isLoading}
            required
          />
        </div>

        <Button
          type="submit"
          variant="primary"
          size="md"
          className="w-full mt-2"
          isLoading={isLoading}
          rightIcon={<ArrowRight className="w-4 h-4" />}
        >
          Sign In with Corporate Credentials
        </Button>
      </form>

      <div className="mt-8 pt-6 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400">
        <div className="flex items-center space-x-1 text-[11px]">
          <ShieldCheck className="w-3.5 h-3.5 text-indigo-400" />
          <span>HMAC-SHA256 JWT RBAC</span>
        </div>
        <Link to="/register" className="text-indigo-400 hover:text-indigo-300 font-semibold hover:underline">
          Register New Account
        </Link>
      </div>
    </div>
  );
};
