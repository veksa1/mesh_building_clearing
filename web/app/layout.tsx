import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Mesh Building Clearing — Tactical Drone Sim',
  description: 'Autonomous BFS-based drone swarm building clearance with RSSI mesh visualization.',
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="h-full bg-black">
      <body className="h-full bg-black text-white font-mono overflow-hidden antialiased">
        {children}
      </body>
    </html>
  );
}
