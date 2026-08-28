import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Lock, Mail, Eye, EyeOff, Shield, ArrowRight, CheckCircle2 } from 'lucide-react';
import { useAuth } from '../hooks/useAuth';
import { useToast } from '../hooks/useToast';
import { Button } from '../components/common/Button';
import { Input } from '../components/common/Input';
import { ApiError } from '../types/api';

export const RegisterPage: React.FC = () => {
  const { register } = useAuth();
  const { success } = useToast();
  const navigate = useNavigate();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);
  const [error, setError] = useState<{ message: string; requestId?: string | null } | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!email.trim()) {
      setError({ message: 'Please enter a corporate email address.' });
      return;
    }

    if (password.length < 8) {
      setError({ message: 'Password must be at least 8 characters long.' });
      return;
    }

    if (password !== confirmPassword) {
      setError({ message: 'Passwords do not match.' });
      return;
    }

    setIsLoading(true);
    try {
      // Per Phase 10 security rules: self-registration is strictly restricted to Employee role (Level 1 clearance)
      await register({
        email: email.trim(),
        password,
        role_names: ['Employee'],
      });

      setIsSuccess(true);
      success('Account Created', 'Your enterprise account was registered successfully.');
      setTimeout(() => {
        navigate('/login');
      }, 2000);
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      setError({
        message: apiErr.message || 'Failed to register corporate account.',
        requestId: apiErr.requestId,
      });
    } finally {
      setIsLoading(false);
    }
  };

  if (isSuccess) {
    return (
      <div className="bg-slate-900 border border-slate-800 p-8 rounded-2xl shadow-2xl text-center">
        <div className="w-12 h-12 rounded-full bg-emerald-950 border border-emerald-800 text-emerald-400 flex items-center justify-center mx-auto mb-4">
          <CheckCircle2 className="w-6 h-6" />
        </div>
        <h2 className="text-xl font-bold text-white tracking-tight">Registration Complete</h2>
        <p className="text-xs text-slate-400 mt-2">
          Your Employee account has been provisioned with Level 1 clearance. Redirecting you to sign in...
        </p>
        <div className="mt-6">
          <Button variant="primary" size="md" onClick={() => navigate('/login')}>
            Proceed to Sign In
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-slate-900 border border-slate-800 p-8 rounded-2xl shadow-2xl">
      <div className="text-left mb-8">
        <h2 className="text-2xl font-bold text-white tracking-tight">Register Account</h2>
        <p className="text-xs text-slate-400 mt-1.5">
          Create a new Employee account with baseline Level 1 security clearance.
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
          label="Corporate Email Address"
          type="email"
          autoComplete="email"
          placeholder="new.user@enterprise.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          leftIcon={<Mail className="w-4 h-4" />}
          disabled={isLoading}
          required
        />

        <div className="relative">
          <Input
            label="Password (min. 8 characters)"
            type={showPassword ? 'text' : 'password'}
            autoComplete="new-password"
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

        <Input
          label="Confirm Password"
          type={showPassword ? 'text' : 'password'}
          autoComplete="new-password"
          placeholder="••••••••"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          leftIcon={<Lock className="w-4 h-4" />}
          disabled={isLoading}
          required
        />

        {/* Security Assurance Pill */}
        <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 flex items-center space-x-2 text-[11px] text-slate-400">
          <Shield className="w-4 h-4 text-indigo-400 shrink-0" />
          <span>Privilege escalation defense: Initial role is restricted to Employee (L1).</span>
        </div>

        <Button
          type="submit"
          variant="primary"
          size="md"
          className="w-full mt-2"
          isLoading={isLoading}
          rightIcon={<ArrowRight className="w-4 h-4" />}
        >
          Create Corporate Account
        </Button>
      </form>

      <div className="mt-8 pt-6 border-t border-slate-800 text-center text-xs text-slate-400">
        Already registered?{' '}
        <Link to="/login" className="text-indigo-400 hover:text-indigo-300 font-semibold hover:underline">
          Sign In
        </Link>
      </div>
    </div>
  );
};
