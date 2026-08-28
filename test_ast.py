from automigrate.mcp_server.tools.apply_ast_transform import apply_ast_transform_to_string
import sys

def main():
    template = '<p *ngIf="isLoggedIn">Welcome back!</p>'
    res = apply_ast_transform_to_string(template)
    print("OUTPUT:", repr(res.transformed_content))

if __name__ == '__main__':
    main()
