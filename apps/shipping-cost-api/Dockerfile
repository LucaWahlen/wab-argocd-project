FROM golang:1.25-alpine AS build
WORKDIR /src
COPY go.mod ./
COPY cmd ./cmd
COPY internal ./internal
RUN CGO_ENABLED=0 go build -trimpath -o /out/shipping-cost-api ./cmd/shipping-cost-api

FROM alpine:3
COPY --from=build /out/shipping-cost-api /shipping-cost-api
EXPOSE 8080
ENTRYPOINT ["/shipping-cost-api"]
