import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";

const TABS = [
  { to: "/", label: "대시보드", icon: "🔔", end: true },
  { to: "/maintenance", label: "정비 승인", icon: "🛠️" },
];

function useClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(id);
  }, []);
  return now;
}

/**
 * Alerts land on a phone, so this reviews like one: a fixed-size "device"
 * (bezel + notch appear only on a wide/desktop viewport - see .phone-frame in
 * app.css) with its own status bar, scrollable screen, and bottom tab bar
 * instead of a normal desktop nav header.
 */
export default function Layout({ children }) {
  const now = useClock();
  const time = now.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false });

  return (
    <div className="phone-viewport">
      <div className="phone-frame">
        <div className="phone-notch" />
        <div className="status-bar">
          <span>{time}</span>
          <span className="status-icons">
            <span>📶</span>
            <span>🔋</span>
          </span>
        </div>
        <header className="app-header">
          <div className="app-header-inner">
            <p className="app-title">산업 설비 안전</p>
            <span className="app-header-badge">4대 설비 모니터링</span>
          </div>
        </header>
        <main className="app-main">{children}</main>
        <nav className="tab-bar">
          {TABS.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              end={tab.end}
              className={({ isActive }) => (isActive ? "active" : undefined)}
            >
              <span className="tab-icon">{tab.icon}</span>
              <span>{tab.label}</span>
            </NavLink>
          ))}
        </nav>
      </div>
    </div>
  );
}
