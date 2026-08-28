# React Class Components → Hooks Migration Guide

React 16.8 introduced Hooks, which allow functional components to use state
and lifecycle features. Class components still work but Hooks are now preferred.

---

## 1. State — `this.state` → `useState`

```jsx
// Class
class Counter extends Component {
  constructor(props) {
    super(props);
    this.state = { count: 0, name: 'Alice' };
  }
}

// Functional — each state field becomes its own Hook
function Counter() {
  const [count, setCount] = useState(0);
  const [name, setName] = useState('Alice');
}
```

---

## 2. Lifecycle Methods → `useEffect`

```jsx
// Class
componentDidMount()  { /* runs once after mount */ }
componentDidUpdate(prevProps, prevState) { /* runs on update */ }
componentWillUnmount() { /* cleanup */ }

// Functional
useEffect(() => {
  // componentDidMount + componentDidUpdate combined
  return () => {
    // componentWillUnmount (cleanup)
  };
}, [dependency]); // [] = run once (mount only)
```

---

## 3. Props — `this.props` → Function Parameters

```jsx
// Class
class Greeting extends Component {
  render() { return <h1>Hello {this.props.name}</h1>; }
}

// Functional
function Greeting({ name }) {
  return <h1>Hello {name}</h1>;
}
```

---

## 4. Refs — `createRef` → `useRef`

```jsx
// Class
class Input extends Component {
  constructor(props) {
    super(props);
    this.inputRef = React.createRef();
  }
}

// Functional
function Input() {
  const inputRef = useRef(null);
}
```

---

## 5. Event Handlers — Remove `this` Binding

```jsx
// Class
class Button extends Component {
  handleClick = () => { /* ... */ }
  render() { return <button onClick={this.handleClick}>Click</button>; }
}

// Functional
function Button() {
  const handleClick = () => { /* ... */ };
  return <button onClick={handleClick}>Click</button>;
}
```

---

## 6. Context — `contextType` → `useContext`

```jsx
// Class
class ThemeButton extends Component {
  static contextType = ThemeContext;
  render() { return <div style={{ color: this.context.color }} />; }
}

// Functional
function ThemeButton() {
  const { color } = useContext(ThemeContext);
  return <div style={{ color }} />;
}
```

---

## 7. `PureComponent` → `React.memo`

```jsx
// Class
class ExpensiveList extends PureComponent { ... }

// Functional
const ExpensiveList = React.memo(function ExpensiveList(props) { ... });
```

---

## Common Hook Equivalents

| Class API | Hook Equivalent |
|---|---|
| `this.state` | `useState` |
| `this.setState` | Setter from `useState` |
| `componentDidMount` | `useEffect(() => {}, [])` |
| `componentDidUpdate` | `useEffect(() => {}, [deps])` |
| `componentWillUnmount` | `return () => {}` inside `useEffect` |
| `createRef` | `useRef` |
| `contextType` | `useContext` |
| `PureComponent` | `React.memo` |
| `getDerivedStateFromProps` | `useMemo` or inline derivation |
| `shouldComponentUpdate` | `React.memo` with comparator |
