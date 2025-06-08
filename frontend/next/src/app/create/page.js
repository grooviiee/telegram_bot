"use client"
import { useRouter } from "next/navigation";

export default function Create(){
    const route = useRouter();

    return (
        <form onSubmit={(e) =>{
            e.preventDefault();
            const title = e.target.title.value;
            const author = e.target.author.value;
            const options = {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({title, author})
            }
            fetch(`http://localhost:9999/topics`, options)
            .then(res=>res.json())
            .then(result=>{
                console.log(result);
                const lastid = result.id
                Router.push(`read/${lastid}`)
            })
        }}>
            <p>
                <input type="text" name="title" placeholder="title" />
            </p>
            <p>
                <textarea name="author" placeholder="author"></textarea>
            </p>
            <p>
                <input type="submit" value="create" />  
            </p>
        </form>
    )
}