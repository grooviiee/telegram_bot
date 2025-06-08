"use client"
import Link from 'next/link';
import { useParams } from 'next/navigation';

export function Control() {
  const params = useParams();
  const id = params.id;

  return (
    <ul>
      <h1> --- Control --- </h1>
      <li><Link href="/create">Go to Create</Link></li>
      {id ? <>
        <li><Link href="/homepage">Go to Homepage</Link></li>
        <li><Link href="/dividend">Go to Dividend check</Link></li>
        <li><input type="button" value="delete"></input></li>
      </> : null}
    </ul>
  );
}
