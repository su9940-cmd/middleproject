import { NavLink } from "react-router-dom";

const NAV_LINKS = [
  { to: "/", label: "대시보드", end: true },
  { to: "/maintenance", label: "정비 승인 대기" },
];

export default function Layout({ children }) {
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header-inner">
          <p className="app-title">산업 설비 안전 대시보드</p>
          <nav className="app-nav">
            {NAV_LINKS.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.end}
                className={({ isActive }) => (isActive ? "active" : undefined)}
              >
                {link.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main className="app-main">{children}</main>
    </div>
  );
}
