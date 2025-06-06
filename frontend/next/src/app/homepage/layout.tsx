export default function Layout(props){
    return (
        <form>
            <h2>Create</h2>
            <img src="/hello.jpeg"></img>
            {props.children}
        </form>
    )
}