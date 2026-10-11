import type {Metadata} from 'next';
import './globals.css';
import {Header} from '@/components/ui';
export const metadata:Metadata={title:'HackConnect AI — Build your dream team',description:'Discover verified hackathons, find complementary teammates, and collaborate in a persistent squad workspace.'};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en" suppressHydrationWarning><body><Header/>{children}<footer><a href="/">HackConnect<span> AI</span></a><p>Find your people. Build something that matters.</p><nav><a href="/privacy">Privacy</a><a href="/terms">Terms</a><a href="/dashboard?tab=support">Support</a></nav></footer></body></html>}
