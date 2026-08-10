import { SiteNav } from "@/components/SiteNav";
import { Footer } from "@/components/Footer";
import { Hero } from "@/components/landing/Hero";
import { WhoItsFor } from "@/components/landing/WhoItsFor";
import { HowItWorks } from "@/components/landing/HowItWorks";
import { WhatItChecks } from "@/components/landing/WhatItChecks";
import { FinalCta } from "@/components/landing/FinalCta";

export default function Landing() {
  return (
    <>
      <SiteNav />
      <main>
        <Hero />
        <WhoItsFor />
        <HowItWorks />
        <WhatItChecks />
        <FinalCta />
      </main>
      <Footer />
    </>
  );
}
