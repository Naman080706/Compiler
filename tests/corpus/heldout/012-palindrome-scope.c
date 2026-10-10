#include <stdio.h>

int main(void) {
    int n = 12321;
    int original = n;
    int reversed = 0;
    while (n > 0) {
        int digit = n % 10;
        reversed = reversed * 10 + digit;
        n = n / 10;
    }
    printf("last digit processed: %d\n", digit);
    if (digit == 1) {
        printf("it ended on 1\n");
    }
    printf("digit squared %d\n", digit * digit);
    printf("reversed = %d\n", reversed);
    if (reversed == original) {
        printf("%d is a palindrome\n", original);
    }
    return 0;
}
