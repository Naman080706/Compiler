#include <stdio.h>

int main(void) {
    double principal = 2500.0;
    double rate = 4.5;
    int years = 3;
    int year;
    int bonus = 100;
    int interest = principal * rate * years / 100.0;
    for (year = 1; year <= years; year++) {
        printf("after year %d: %f\n", year, principal + principal * rate * year / 100.0);
    }
    printf("simple interest over %d years: %d\n", years, interest);
    printf("principal was %f at %f percent\n", principal, rate);
    return 0;
}
