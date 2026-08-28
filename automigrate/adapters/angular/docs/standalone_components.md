# Angular Standalone Components Migration Guide

Angular 15+ introduced standalone components, directives, and pipes that
do not need to be declared in an NgModule.

---

## 1. Making a Component Standalone

```typescript
// Legacy (NgModule-based)
@Component({
  selector: 'app-user',
  templateUrl: './user.component.html',
})
export class UserComponent {}

@NgModule({
  declarations: [UserComponent],
  imports: [CommonModule, RouterModule],
})
export class UserModule {}

// New (Standalone)
@Component({
  selector: 'app-user',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './user.component.html',
})
export class UserComponent {}
```

---

## 2. Bootstrapping a Standalone App

```typescript
// Legacy
platformBrowserDynamic().bootstrapModule(AppModule);

// New
bootstrapApplication(AppComponent, {
  providers: [
    provideRouter(routes),
    provideHttpClient(),
  ],
});
```

---

## 3. Routing with Standalone Components

```typescript
// New: use loadComponent for lazy loading
{
  path: 'users',
  loadComponent: () =>
    import('./users/users.component').then(m => m.UsersComponent),
}
```
