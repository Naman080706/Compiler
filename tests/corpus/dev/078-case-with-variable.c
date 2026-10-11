#include <stdio.h>

int main(void) {
    int choice = 2;
    int target = 2;
    switch (choice) {
        case target:
            printf("match\n");
            break;
        default:
            printf("no match\n");
    }
    return 0;
}
