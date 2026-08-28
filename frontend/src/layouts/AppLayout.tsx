import React, { useState } from 'react';
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  FileText,
  Search,
  BotMessageSquare,
  GitCompare,
  ShieldAlert,
  User,
  LogOut,
  Menu,
  X,
  Sun,
  Moon,
  Shield,
  Building2,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { useAuth } from '../hooks/useAuth';
import { Badge } from '../components/common/Badge';
import { storage } from '../utils/storage';
import { cn } from '../utils/cn';

export const AppLayout: React.FC = () => {
  const { user, isAdmin, clearanceLevel, departmentName, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState<boolean>(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState<boolean>(false);
  const [theme, setTheme] = useState<'light' | 'dark'>(() => storage.getTheme());

  const toggleTheme = () => {
    const nextTheme = theme === 'dark' ? 'light' : 'dark';
    setTheme(nextTheme);
    storage.setTheme(nextTheme);
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const navItems = [
    { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { to: '/documents', label: 'Documents', icon: FileText },
    { to: '/search', label: 'Search', icon: Search },
    { to: '/rag', label: 'AI Assistant', icon: BotMessageSquare },
    { to: '/compare', label: 'Compare Documents', icon: GitCompare },
    ...(isAdmin ? [{ to: '/audit', label: 'Audit & Security', icon: ShieldAlert, adminOnly: true }] : []),
    { to: '/profile', label: 'Profile', icon: User },
  ];

  const getClearanceVariant = (level: number) => {
    switch (level) {
      case 4:
        return 'rose';
      case 3:
        return 'purple';
      case 2:
        return 'indigo';
      default:
        return 'slate';
    }
  };

  return (
    <div className="min-h-screen flex bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100">
      {/* Mobile Backdrop */}
      {isMobileMenuOpen && (
        <div
          className="fixed inset-0 z-40 bg-slate-900/60 backdrop-blur-sm lg:hidden"
          onClick={() => setIsMobileMenuOpen(false)}
        />
      )}

      {/* Sidebar Navigation */}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-50 flex flex-col bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 transition-all duration-300 lg:static',
          isSidebarCollapsed ? 'w-20' : 'w-64',
          isMobileMenuOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        )}
      >
        {/* Brand Header */}
        <div className="h-16 flex items-center justify-between px-4 border-b border-slate-100 dark:border-slate-800">
          <div className="flex items-center space-x-3 overflow-hidden">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 to-indigo-400 flex items-center justify-center text-white font-bold shadow-md shrink-0">
              EDI
            </div>
            {!isSidebarCollapsed && (
              <div className="truncate">
                <span className="font-bold text-sm tracking-tight text-slate-900 dark:text-white block leading-tight">
                  Enterprise AI
                </span>
                <span className="text-[10px] text-slate-400 font-mono tracking-wider uppercase block">
                  Doc Intelligence
                </span>
              </div>
            )}
          </div>

          <button
            onClick={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
            className="hidden lg:flex p-1 rounded-lg text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            title={isSidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {isSidebarCollapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
          </button>

          <button
            onClick={() => setIsMobileMenuOpen(false)}
            className="lg:hidden p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* User Clearance & Department Badge */}
        {!isSidebarCollapsed && user && (
          <div className="p-3.5 mx-3 mt-3 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200/60 dark:border-slate-800">
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-500 dark:text-slate-400 truncate max-w-[120px]">
                {user.email}
              </span>
              <Badge variant={getClearanceVariant(clearanceLevel)} size="sm">
                L{clearanceLevel}
              </Badge>
            </div>
            <div className="mt-2 flex items-center space-x-1.5 text-[11px] text-slate-600 dark:text-slate-300">
              <Building2 className="w-3.5 h-3.5 text-slate-400" />
              <span className="truncate">{departmentName}</span>
            </div>
          </div>
        )}

        {/* Navigation Items */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname.startsWith(item.to);

            return (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={() => setIsMobileMenuOpen(false)}
                className={cn(
                  'flex items-center space-x-3 px-3 py-2.5 rounded-xl text-xs font-semibold transition-all select-none',
                  isActive
                    ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-500/20'
                    : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800/80 hover:text-slate-900 dark:hover:text-slate-100',
                  isSidebarCollapsed && 'justify-center px-2'
                )}
                title={isSidebarCollapsed ? item.label : undefined}
              >
                <Icon className={cn('w-4 h-4 shrink-0', isActive ? 'text-white' : 'text-slate-500')} />
                {!isSidebarCollapsed && <span>{item.label}</span>}
                {!isSidebarCollapsed && item.adminOnly && (
                  <span className="ml-auto text-[10px] font-mono px-1.5 py-0.2 rounded bg-rose-100 dark:bg-rose-950 text-rose-700 dark:text-rose-300 border border-rose-300 dark:border-rose-800">
                    ADMIN
                  </span>
                )}
              </NavLink>
            );
          })}
        </nav>

        {/* Sidebar Footer */}
        <div className="p-3 border-t border-slate-100 dark:border-slate-800 space-y-1">
          <button
            onClick={toggleTheme}
            className={cn(
              'w-full flex items-center space-x-3 px-3 py-2 rounded-xl text-xs text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors',
              isSidebarCollapsed && 'justify-center px-2'
            )}
            title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {theme === 'dark' ? <Sun className="w-4 h-4 shrink-0 text-amber-400" /> : <Moon className="w-4 h-4 shrink-0" />}
            {!isSidebarCollapsed && <span>{theme === 'dark' ? 'Light Mode' : 'Dark Mode'}</span>}
          </button>

          <button
            onClick={handleLogout}
            className={cn(
              'w-full flex items-center space-x-3 px-3 py-2 rounded-xl text-xs text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-colors',
              isSidebarCollapsed && 'justify-center px-2'
            )}
            title="Log out"
          >
            <LogOut className="w-4 h-4 shrink-0" />
            {!isSidebarCollapsed && <span>Sign Out</span>}
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top Header */}
        <header className="h-16 bg-white/80 dark:bg-slate-900/80 backdrop-blur-md border-b border-slate-200 dark:border-slate-800 flex items-center justify-between px-4 lg:px-8 z-20">
          <div className="flex items-center space-x-3">
            <button
              onClick={() => setIsMobileMenuOpen(true)}
              className="lg:hidden p-2 rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
              aria-label="Open mobile menu"
            >
              <Menu className="w-5 h-5" />
            </button>

            <button
              onClick={() => navigate('/search')}
              className="hidden sm:flex items-center space-x-2 text-xs text-slate-400 bg-slate-100 dark:bg-slate-800/80 px-3.5 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700/80 hover:border-slate-300 dark:hover:border-slate-600 transition-colors"
            >
              <Search className="w-3.5 h-3.5" />
              <span>Search knowledge base...</span>
              <kbd className="font-mono bg-white dark:bg-slate-900 px-1.5 py-0.5 rounded text-[10px] border border-slate-200 dark:border-slate-700">
                /
              </kbd>
            </button>
          </div>

          <div className="flex items-center space-x-3">
            {user && (
              <div className="flex items-center space-x-2 bg-slate-100/70 dark:bg-slate-800/60 pl-3 pr-2 py-1.5 rounded-full border border-slate-200 dark:border-slate-700">
                <span className="text-xs font-medium text-slate-700 dark:text-slate-200 truncate max-w-[150px]">
                  {user.email}
                </span>
                <Badge variant={getClearanceVariant(clearanceLevel)} size="sm">
                  <Shield className="w-3 h-3" />
                  <span>Clearance L{clearanceLevel}</span>
                </Badge>
              </div>
            )}
          </div>
        </header>

        {/* Routed Page Content */}
        <main className="flex-1 overflow-y-auto p-4 lg:p-8">
          <div className="max-w-7xl mx-auto">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
};
