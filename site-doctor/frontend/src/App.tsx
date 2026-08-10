import { useEffect } from "react";
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import Landing from "@/pages/Landing";
import AuditApp from "@/pages/AuditApp";

/** Router doesn't handle hash targets or restore scroll on navigation, so
 *  do both here: jump to the anchor if there is one, top of page if not. */
function ScrollBehaviour() {
  const { pathname, hash } = useLocation();

  useEffect(() => {
    if (hash) {
      const target = document.querySelector(hash);
      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        return;
      }
    }
    window.scrollTo({ top: 0 });
  }, [pathname, hash]);

  return null;
}

export default function App() {
  return (
    <BrowserRouter>
      <ScrollBehaviour />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/app" element={<AuditApp />} />
        {/* Anything else is a mistyped URL; the landing page is the safest
            place to put someone who is lost. */}
        <Route path="*" element={<Landing />} />
      </Routes>
    </BrowserRouter>
  );
}
