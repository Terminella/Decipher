import FindingsPage from './pages/FindingsPage'
import { useEffect, useState } from 'react'
import DossierPage from './pages/DossierPage'
import UploadPage from './pages/UploadPage'
import InvestigationPage from './pages/InvestigationPage'
import SettingsPage from './pages/SettingsPage'

import {
  LayoutDashboard,
  FolderSearch,
  Upload,
  FileSearch,
  FileText,
  Settings,
  Bell,
  Search,
  Plus,
  ArrowUpRight,
  Files,
  AlertTriangle,
  ClipboardCheck,
  Clock3,
  MoreHorizontal,
  ChevronRight,
  ShieldCheck,
  Activity,
  Menu,
  X,
} from 'lucide-react'

// ==========================================
// NAVIGATION
// ==========================================

const navigation = [
  { name: 'Dashboard', icon: LayoutDashboard },
  { name: 'Investigations', icon: FolderSearch },
  { name: 'Upload Documents', icon: Upload },
  { name: 'Findings', icon: FileSearch },
  { name: 'Dossiers & Reports', icon: FileText },
]

// ==========================================
// EMPTY DASHBOARD STATISTICS
// ==========================================

const statistics = [
  {
    title: 'Total Investigations',
    value: 0,
    description: 'No investigations created yet',
    icon: FolderSearch,
    color: 'teal',
  },
  {
    title: 'Documents Analyzed',
    value: 0,
    description: 'No documents uploaded yet',
    icon: Files,
    color: 'purple',
  },
  {
    title: 'Suspicious Findings',
    value: 0,
    description: 'No findings available',
    icon: AlertTriangle,
    color: 'amber',
  },
  {
    title: 'Completed Reviews',
    value: 0,
    description: 'No reviews completed yet',
    icon: ClipboardCheck,
    color: 'coral',
  },
]

// Empty data collections.
// Real data can be connected later.

const investigations = []
const activities = []

// ==========================================
// STATUS BADGE
// ==========================================

function StatusBadge({ status, color }) {
  return (
    <span className={`status-badge status-${color}`}>
      <span className="status-dot" />
      {status}
    </span>
  )
}

// ==========================================
// SIDEBAR
// ==========================================

function Sidebar({
  activePage,
  setActivePage,
  mobileOpen,
  setMobileOpen,
}) {
  return (
    <>
      {mobileOpen && (
        <div
          className="mobile-overlay"
          onClick={() => setMobileOpen(false)}
        />
      )}

      <aside
        className={`sidebar ${mobileOpen ? 'sidebar-open' : ''}`}
      >
        <div className="brand">
          <div className="brand-icon">
            <ShieldCheck size={24} />
          </div>

          <div>
            <h2>DECIPHER</h2>
            <span>DOCUMENT INTELLIGENCE</span>
          </div>

          <button
            className="mobile-close"
            onClick={() => setMobileOpen(false)}
            aria-label="Close navigation"
          >
            <X size={20} />
          </button>
        </div>

        <div className="sidebar-label">WORKSPACE</div>

        <nav className="navigation">
          {navigation.map((item) => {
            const Icon = item.icon
            const active = activePage === item.name

            return (
              <button
                key={item.name}
                className={`nav-item ${
                  active ? 'nav-active' : ''
                }`}
                onClick={() => {
                  setActivePage(item.name)
                  setMobileOpen(false)
                }}
              >
                <Icon size={20} strokeWidth={1.8} />
                <span>{item.name}</span>
              </button>
            )
          })}
        </nav>

        <div className="sidebar-bottom">
          <div className="sidebar-label">PREFERENCES</div>

          <button
            className={`nav-item ${
              activePage === 'Settings' ? 'nav-active' : ''
            }`}
            onClick={() => {
              setActivePage('Settings')
              setMobileOpen(false)
            }}
          >
            <Settings size={20} />
            <span>Settings</span>
          </button>

          <div className="sidebar-profile">
            <div className="profile-avatar">U</div>

            <div className="profile-info">
              <strong>Workspace User</strong>
              <span>Decipher Workspace</span>
            </div>

            <MoreHorizontal size={20} />
          </div>
        </div>
      </aside>
    </>
  )
}

// ==========================================
// EMPTY STATE COMPONENT
// ==========================================

function EmptyState({
  icon: Icon,
  title,
  description,
  actionLabel,
  onAction,
}) {
  return (
    <div className="empty-state">
      <Icon size={32} />

      <strong>{title}</strong>

      <span>{description}</span>

      {actionLabel && (
        <button
          className="button-primary"
          onClick={onAction}
        >
          <Plus size={17} />
          {actionLabel}
        </button>
      )}
    </div>
  )
}

// ==========================================
// DASHBOARD
// ==========================================

function Dashboard({ onNavigate }) {
  return (
    <>
      {/* Welcome Section */}

      <div className="welcome-section">
        <div>
          <div className="eyebrow">
            <span className="live-dot" />
            INVESTIGATION OVERVIEW
          </div>

          <h1>Welcome to Decipher</h1>

          <p>
            Your document intelligence and forensic
            investigation workspace.
          </p>
        </div>

        <div className="welcome-actions">
          <button
            className="button-secondary"
            onClick={() => onNavigate('Upload Documents')}
          >
            <Upload size={18} />
            Upload Documents
          </button>

          <button
            className="button-primary"
            onClick={() => onNavigate('New Investigation')}
          >
            <Plus size={19} />
            New Investigation
          </button>
        </div>
      </div>

      {/* Statistics */}

      <div className="stats-grid">
        {statistics.map((stat) => {
          const Icon = stat.icon

          return (
            <div className="stat-card" key={stat.title}>
              <div className="stat-top">
                <div className={`stat-icon icon-${stat.color}`}>
                  <Icon size={23} />
                </div>

                <button
                  className="stat-action"
                  onClick={() =>
                    onNavigate(
                      stat.title === 'Suspicious Findings'
                        ? 'Findings'
                        : 'Investigations'
                    )
                  }
                  aria-label={`View ${stat.title}`}
                >
                  <ArrowUpRight size={19} />
                </button>
              </div>

              <div className="stat-value">{stat.value}</div>

              <div className="stat-title">
                {stat.title}
              </div>

              <div className="stat-footer">
                <span>{stat.description}</span>
              </div>
            </div>
          )
        })}
      </div>

      {/* Main Dashboard Content */}

      <div className="content-grid">

        {/* Recent Investigations */}

        <section className="panel investigations-panel">
          <div className="panel-header">
            <div>
              <h3>Recent Investigations</h3>
              <p>
                Access and manage your document investigations.
              </p>
            </div>

            <button
              className="text-action"
              onClick={() => onNavigate('Investigations')}
            >
              View all <ChevronRight size={17} />
            </button>
          </div>

          <div className="table-scroll">
            <table className="investigation-table">
              <thead>
                <tr>
                  <th>INVESTIGATION</th>
                  <th>DOCUMENTS</th>
                  <th>DATE</th>
                  <th>STATUS</th>
                  <th>ACTION</th>
                </tr>
              </thead>

              <tbody>
                {investigations.length > 0 ? (
                  investigations.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <div className="investigation-name">
                          <strong>{item.name}</strong>
                          <span>
                            {item.id} · {item.type}
                          </span>
                        </div>
                      </td>

                      <td>{item.documents} files</td>

                      <td>{item.date}</td>

                      <td>
                        <StatusBadge
                          status={item.status}
                          color={item.color}
                        />
                      </td>

                      <td>
                        <button
                          className="table-action"
                          onClick={() =>
                            onNavigate(
                              `Investigation: ${item.name}`
                            )
                          }
                        >
                          <ArrowUpRight size={18} />
                        </button>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan="5">
                      <EmptyState
                        icon={FolderSearch}
                        title="No investigations yet"
                        description="Create your first investigation to get started."
                        actionLabel="Create Investigation"
                        onAction={() =>
                          onNavigate('New Investigation')
                        }
                      />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        {/* Recent Activity */}

        <section className="panel activity-panel">
          <div className="panel-header">
            <div>
              <h3>Recent Activity</h3>
              <p>Track your latest workspace activities.</p>
            </div>

            <Activity
              size={21}
              className="activity-heading-icon"
            />
          </div>

          <div className="activity-list">
            {activities.length > 0 ? (
              activities.map((activity, index) => {
                const Icon = activity.icon

                return (
                  <div
                    className="activity-item"
                    key={index}
                  >
                    <div
                      className={`activity-icon icon-${activity.color}`}
                    >
                      <Icon size={18} />
                    </div>

                    <div className="activity-details">
                      <strong>{activity.title}</strong>
                      <span>{activity.detail}</span>

                      <small>
                        <Clock3 size={13} />
                        {activity.time}
                      </small>
                    </div>
                  </div>
                )
              })
            ) : (
              <div className="empty-activity">
                <Activity size={30} />

                <strong>No recent activity</strong>

                <span>
                  Your workspace activity will appear here
                  when you start an investigation.
                </span>
              </div>
            )}
          </div>

          <button
            className="activity-footer"
            onClick={() => onNavigate('Recent Activity')}
          >
            View activity history
            <ChevronRight size={17} />
          </button>
        </section>
      </div>

      {/* Bottom Information Banner */}

      <div className="bottom-banner">
        <div className="banner-icon">
          <ShieldCheck size={26} />
        </div>

        <div className="banner-content">
          <strong>
            Document intelligence, beyond OCR.
          </strong>

          <span>
            Analyze documents, investigate anomalies
            and uncover contextual discrepancies.
          </span>
        </div>

        <button
          className="banner-action"
          onClick={() => onNavigate('Upload Documents')}
        >
          Get started
          <ArrowUpRight size={17} />
        </button>
      </div>
    </>
  )
}

// ==========================================
// PLACEHOLDER PAGES
// ==========================================

function PlaceholderPage({ page, onNavigate }) {
  const pageIcons = {
    'Upload Documents': Upload,
    Investigations: FolderSearch,
    Findings: FileSearch,
    'Dossiers & Reports': FileText,
    Settings: Settings,
    'New Investigation': FolderSearch,
    'Recent Activity': Activity,
  }

  const Icon = pageIcons[page] || FileSearch

  const isNewInvestigation = page === 'New Investigation'

  return (
    <div className="placeholder-panel">
      <div className="placeholder-icon">
        <Icon size={34} />
      </div>

      <h2>{page}</h2>

      <p>
        {isNewInvestigation
          ? 'Start a new document investigation and organize your evidence.'
          : `The ${page} workspace is ready for development.`}
      </p>

      <button
        className="button-primary"
        onClick={() => onNavigate('Dashboard')}
      >
        <LayoutDashboard size={18} />
        Return to Dashboard
      </button>
    </div>
  )
}

// ==========================================
// MAIN APPLICATION
// ==========================================

export default function App() {
  const [activePage, setActivePage] = useState('Dashboard')
  const [mobileOpen, setMobileOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [notificationOpen, setNotificationOpen] = useState(false)

  // ==========================================
  // GLOBAL THEME SETTINGS
  // ==========================================

  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('decipher-theme') || 'dark'
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('decipher-theme', theme)
  }, [theme])

  const navigate = (page) => {
    setActivePage(page)
    setMobileOpen(false)
    setNotificationOpen(false)
  }

  return (
    <div className="app-shell">

      {/* Sidebar */}

      <Sidebar
        activePage={activePage}
        setActivePage={navigate}
        mobileOpen={mobileOpen}
        setMobileOpen={setMobileOpen}
      />

      {/* Main Area */}

      <main className="main-area">

        {/* Top Navigation */}

        <header className="topbar">
          <div className="topbar-left">
            <button
              className="mobile-menu"
              onClick={() => setMobileOpen(true)}
              aria-label="Open navigation"
            >
              <Menu size={22} />
            </button>

            <div className="breadcrumb">
              Workspace
              <ChevronRight size={15} />
              <strong>{activePage}</strong>
            </div>
          </div>

          <div className="topbar-right">

            {/* Search */}

            <div className="search-box">
              <Search size={18} />

              <input
                value={search}
                onChange={(event) =>
                  setSearch(event.target.value)
                }
                placeholder="Search investigations..."
              />

              <kbd>Ctrl K</kbd>
            </div>

            {/* Notifications */}

            <div className="notification-wrapper">
              <button
                className="notification-button"
                onClick={() =>
                  setNotificationOpen(!notificationOpen)
                }
                aria-label="Notifications"
              >
                <Bell size={20} />
              </button>

              {notificationOpen && (
                <div className="notification-popover">
                  <strong>Notifications</strong>

                  <p>
                    You're all caught up. No new notifications.
                  </p>
                </div>
              )}
            </div>

            {/* Profile */}

            <div className="topbar-avatar">U</div>
          </div>
        </header>

        {/* Page Content */}

        <div className="page-content">
  {activePage === 'Dashboard' ? (
    <Dashboard onNavigate={navigate} />
  ) : activePage === 'Upload Documents' ? (
    <UploadPage />
  ) : activePage === 'Investigations' ? (
    <InvestigationPage onNavigate={navigate} />
  ) : activePage === 'Findings' ? (
    <FindingsPage />
  ) : activePage === 'Dossiers & Reports' ? (
    <DossierPage />
  ) : activePage === 'Settings' ? (
    <SettingsPage
      theme={theme}
      onThemeChange={setTheme}
    />
  ) : (
    <PlaceholderPage
      page={activePage}
      onNavigate={navigate}
    />
  )}

          {/* Footer */}

          <footer className="app-footer">
            <span>DECIPHER DOCUMENT INTELLIGENCE</span>
            <span>Version 1.0.0 · Development Preview</span>
          </footer>
        </div>
      </main>
    </div>
  )
}
